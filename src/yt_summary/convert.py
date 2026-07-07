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

import re

import opencc

_cc: opencc.OpenCC | None = None

# inline code——單行內要原樣保留。開閉為等長的 backtick run(`code`、``co`de``…),
# 支援 CommonMark 的多-backtick span(內容本身含單 backtick 時用雙 backtick 包)。
_INLINE = re.compile(r"(`+)(?:.+?)\1")
# fenced code:開 fence 3+ 個 ` 或 ~(可帶 info string);閉 fence 同字元、長度 >=、且不帶 info。
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})[ \t]*$")


def to_traditional(text: str) -> str:
    """簡體(或已繁/英文)→ 繁體台灣用語;空值原樣返回。純文字用(標題/表頭)。"""
    if not text:
        return text
    global _cc
    if _cc is None:
        _cc = opencc.OpenCC("s2twp")
    return _cc.convert(text)


def _convert_prose_line(line: str) -> str:
    """轉一行散文,但保留其中的 inline code。"""
    out: list[str] = []
    last = 0
    for m in _INLINE.finditer(line):
        out.append(to_traditional(line[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(to_traditional(line[last:]))
    return "".join(out)


def to_traditional_markdown(md: str) -> str:
    """對 markdown 轉繁,但完整保留 code 區塊(D8:程式碼原樣保留)。

    逐行狀態機:正確處理任意長度的 ``` / ~~~ fence、巢狀 fence(閉合需同字元且
    長度 >=)、以及行內的 inline code——程式碼一律不轉繁,以免改壞原始碼。
    """
    if not md:
        return md
    out: list[str] = []
    fence: tuple[str, int] | None = None  # (字元, 長度)
    for line in md.splitlines(keepends=True):
        if fence is None:
            m = _FENCE_OPEN.match(line)
            if m:
                run = m.group(1)
                fence = (run[0], len(run))
                out.append(line)                    # 開 fence 行:原樣(含 info string)
            else:
                out.append(_convert_prose_line(line))
        else:
            out.append(line)                        # code 內:原樣
            m = _FENCE_CLOSE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
    return "".join(out)
