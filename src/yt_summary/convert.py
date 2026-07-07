"""簡→繁確定性轉換(opencc s2twp,台灣用語)。

字幕常為簡體,但產物一律 zh-TW。這一層把「保證繁體」從靠 LLM 心情(非確定性,
曾整篇簡體)改成查表轉換(100% 穩定),prompt 的繁體指示退為雙保險。

安全性:opencc 只轉中文字——英文、數字、URL 原樣不動(實測)。目前 M1 只收
zh-TW/zh-Hant/zh/en 字幕(見 m1_fetch.DEFAULT_LANG_PRIORITY),送到這裡的內容
只會是中文或(英文來源時)中譯文,都安全。

⚠️ 若未來把 "ja" 加進 m1_fetch.DEFAULT_LANG_PRIORITY 以支援日文,這裡必須加
   來源語言防護——s2twp 會誤轉部分日文漢字(如 変換 等新字體)。
"""
from __future__ import annotations

import opencc

_cc: opencc.OpenCC | None = None


def to_traditional(text: str) -> str:
    """簡體(或已繁/英文)→ 繁體台灣用語;空值原樣返回。"""
    if not text:
        return text
    global _cc
    if _cc is None:
        _cc = opencc.OpenCC("s2twp")
    return _cc.convert(text)
