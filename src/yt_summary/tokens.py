"""啟發式 token 估算(spec 允許 ±10% 誤差,不引入 tokenizer 依賴)。"""
import re

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
_WORD = re.compile(r"[A-Za-z0-9_]+")


def estimate_tokens(text: str) -> int:
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(text))
    return round(cjk * 1.0 + words * 1.3)
