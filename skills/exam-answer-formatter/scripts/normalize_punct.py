#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论述题答案标点/序号机械归一化（首遍）。

仅做确定性强、低风险的转换，降低 AI 后续人工核对负担：
  - 半角序号 (N ) / ( N) -> 全角（N），数字前后无空格
  - 其余半角 () -> 全角 （）
  - 英文 , ; : ! ? -> 中文 ，；：！？
  - 删除中文/全角标点后的多余空格
  - 删除数字与中文单位之间的空格（如 "6 分" -> "6分"）

不做：错别字修正、句号转换、引号转换、短横小点转圆圈序号（这些由 AI 处理）。
注意：刻意不转换英文句号 "."，以免误伤小数（如 3.14）与英文缩写。

用法：
  python3 normalize_punct.py < input.txt > output.txt
  echo "..." | python3 normalize_punct.py
"""
import re
import sys

# 中文/全角标点集合（用于删除其后多余空格）
CN_PUNCT = r'，。；：！？、（）“”‘’《》…—「」『』〔〕【】'

# 数字与中文之间的空格：(\d) + 空格 + (CJK) -> 连写（只匹配空格/制表，不动换行）
DIGIT_SPACE_CJK = re.compile(r'(\d)[ \t]+([\u4e00-\u9fff])')

# 中文/全角标点后的多余空格（只匹配空格/制表，保留换行以维护段落结构）
PUNCT_TRAILING_SPACE = re.compile(r'([' + CN_PUNCT + r'])[ \t]+')

# 半角序号 (N ) / ( N) -> （N）
HALF_BRACKET_NUM = re.compile(r'\(\s*(\d+)\s*\)')


def normalize(text: str) -> str:
    # 1) 半角序号 -> 全角（数字）
    text = HALF_BRACKET_NUM.sub(r'（\1）', text)
    # 2) 其余半角括号 -> 全角（ASCII 与中文括号码点不同，仅影响半角）
    text = text.replace('(', '（').replace(')', '）')
    # 3) 英文标点 -> 中文标点（仅 ASCII）
    for en, zh in (',', '，'), (';', '；'), (':', '：'), ('!', '！'), ('?', '？'):
        text = text.replace(en, zh)
    # 4) 删除中文/全角标点后的多余空格
    text = PUNCT_TRAILING_SPACE.sub(r'\1', text)
    # 5) 删除数字与中文单位之间的空格
    text = DIGIT_SPACE_CJK.sub(r'\1\2', text)
    return text


if __name__ == '__main__':
    data = sys.stdin.read()
    sys.stdout.write(normalize(data))
