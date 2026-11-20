"""Chinese + English tokenizer."""
import re

def tokenize(text):
    text_lower = text.lower()
    words = re.findall(r'[a-z0-9]+', text_lower)
    for ch in text_lower:
        if '\u4e00' <= ch <= '\u9fff':
            words.append(ch)
    for i in range(len(text_lower)-1):
        c1, c2 = text_lower[i], text_lower[i+1]
        if '\u4e00' <= c1 <= '\u9fff' and '\u4e00' <= c2 <= '\u9fff':
            words.append(c1 + c2)
    return words
