import fitz, re, pickle, json
from collections import Counter

CN_NUM = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
          '十一':11,'十二':12,'十三':13,'十四':14,'十五':15}

def is_chap_line(line):
    s=line.strip()
    if not re.match(r'^第[一二三四五六七八九十]+章', s):
        return None
    if any(w in s for w in ['刷题笔记','详见','解析','考点','题刷']):
        return None
    if len(s) > 40:
        return None
    return CN_NUM[re.match(r'^第([一二三四五六七八九十]+)章', s).group(1)]

OPT_MARK = re.compile(r'([A-Ea-e])\s*[．.\u3002]')   # option marker, may be embedded

def split_option_line(text):
    """Given a line that may contain one or more option markers, return list of (letter, text)."""
    matches=list(OPT_MARK.finditer(text))
    if not matches:
        return None
    res=[]
    for i,m in enumerate(matches):
        letter=m.group(1).upper()
        cstart=m.end()
        cend=matches[i+1].start() if i+1<len(matches) else len(text)
        res.append((letter, text[cstart:cend]))
    return res

def parse_questions(pages):
    sec_pat = re.compile(r'^[一二三四]、\s*(单项选择|多项选择)题')
    q_pat = re.compile(r'^(\d+)\s*[．.\u3002]')
    cur_chap=None; cur_sec=None; between=True
    questions={}; order=[]; chap_titles={}
    cur=None  # current (chap,qnum)
    for pi,txt in enumerate(pages):
        for line in txt.split('\n'):
            s=line.strip()
            if not s:
                continue
            c=is_chap_line(line)
            if c is not None:
                cur_chap=c; cur_sec=None; between=True; cur=None
                chap_titles[c]=re.sub(r'^第[一二三四五六七八九十]+章\s*','',s)
                continue
            sm=sec_pat.match(s)
            if sm:
                cur_sec='单选' if sm.group(1)=='单项选择' else '多选'
                between=True; cur=None
                continue
            qm=q_pat.match(s)
            if qm and cur_chap is not None:
                qnum=int(qm.group(1))
                head=s[qm.end():].strip()
                key=(cur_chap,qnum)
                questions[key]={'sec':cur_sec,'text':head,'options':[],'chap':cur_chap}
                order.append(key); cur=key; between=False
                continue
            if between or cur is None:
                continue
            # option line or continuation
            sm_opt=OPT_MARK.match(s)
            if sm_opt:
                # line starts with an option marker (possibly multiple on one line)
                parts=split_option_line(s)
                for letter,otext in parts:
                    questions[cur]['options'].append((letter, otext.strip()))
                continue
            # continuation: append to last option if any, else to text
            if questions[cur]['options']:
                L,oT=questions[cur]['options'][-1]
                parts=split_option_line(s)
                if parts and len(parts)>1:
                    questions[cur]['options'][-1]=(L, (oT+parts[0][1]).strip())
                    for letter,otext in parts[1:]:
                        questions[cur]['options'].append((letter, otext.strip()))
                else:
                    questions[cur]['options'][-1]=(L, (oT+s).strip())
            else:
                questions[cur]['text']+=s
    return questions,order,chap_titles

def parse_answers(pages):
    sec_pat = re.compile(r'^[一二三四]、\s*(单项选择|多项选择)题')
    q_pat = re.compile(r'^(\d+)\s*[．.\u3002]\s*([A-Ea-e]+)')
    cur_chap=None; cur_sec=None
    answers={}; order=[]; buf=None; chap_titles={}
    def flush():
        nonlocal buf
        if buf:
            key=(buf['chap'],buf['qnum'])
            content='\n'.join(l for l in buf['lines']).strip()
            answers[key]={'ans':buf['ans'],'sec':buf['sec'],'content':content}
            order.append(key)
        buf=None
    for pi,txt in enumerate(pages):
        for line in txt.split('\n'):
            line=line.rstrip()
            if not line.strip():
                if buf is not None: buf['lines'].append('')
                continue
            c=is_chap_line(line)
            if c is not None:
                flush(); cur_chap=c; cur_sec=None; chap_titles[c]=re.sub(r'^第[一二三四五六七八九十]+章\s*','',line.strip()); continue
            sm=sec_pat.match(line.strip())
            if sm:
                flush(); cur_sec='单选' if sm.group(1)=='单项选择' else '多选'; continue
            qm=q_pat.match(line)
            if qm and cur_chap is not None:
                flush()
                qnum=int(qm.group(1)); ans=qm.group(2).upper()
                rest=line[qm.end():].strip()
                buf={'chap':cur_chap,'qnum':qnum,'ans':ans,'sec':cur_sec,'lines':[rest] if rest else []}
                continue
            if buf is not None:
                buf['lines'].append(line)
    flush()
    return answers,order,chap_titles

if __name__=='__main__':
    qpages=[fitz.open('720-史纲.pdf')[i].get_text('text') for i in range(len(fitz.open('720-史纲.pdf')))]
    apages=[fitz.open('720-史纲答案.pdf')[i].get_text('text') for i in range(len(fitz.open('720-史纲答案.pdf')))]
    q,oq,qt=parse_questions(qpages)
    a,oa,at=parse_answers(apages)
    chap_titles=qt
    pickle.dump((q,a,chap_titles),open('parsed.pkl','wb'))
    print('QUESTIONS:',len(q),'ANSWERS:',len(a))
    print('CHAPTERS:',dict(sorted(chap_titles.items())))
    cq=Counter(k[0] for k in q); ca=Counter(k[0] for k in a)
    print('per chapter Q:',dict(sorted(cq.items())),' A:',dict(sorted(ca.items())))
    oc=Counter(len(q[k]['options']) for k in q)
    print('option-count:',dict(oc))
    print('mismatch Q-A:',set(q)^set(a))
    # inspect previously buggy
    for k in [(5,10),(4,12)]:
        print('=== Q',k,'===')
        print('TEXT:',q[k]['text'][:100])
        for o in q[k]['options']: print('  ',o[0],o[1][:60])
        print('ANS:',a[k]['ans'])
    print('saved')
