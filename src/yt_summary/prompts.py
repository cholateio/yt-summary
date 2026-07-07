"""所有 LLM prompt 模板;type 特化規則集中此處(design D3)。"""
from __future__ import annotations

TYPE_RULES = {
    "A": "- 保留論點的推理鏈:不只記結論,也要記講者「為什麼」這樣主張。",
    "B": ("- 所有數字、百分比、日期、股票/商品代號、指標名稱必須原樣抄錄,"
          "禁止改寫為「大約」「不錯」等模糊描述。"),
    "C": ("- 程式碼、檔案名稱、函式名、指令列參數原樣保留;"
          "講者口述的實作步驟完整記錄,勿簡化。"),
}

_APPENDIX_RULES = {
    "A": "附錄:提及的工具/資源清單。",
    "B": "附錄「必須」包含:數字彙整表(數值|說明|時間戳)。",
    "C": "附錄「必須」包含:完整程式碼區塊(每塊標對應時間戳)。",
}

_ASR_NOTE = ("本字幕由 ASR 自動產生,可能有錯字:遇疑似錯字依上下文合理推斷,"
             "並將該論點標 confidence: \"low\"。")

# 最終文章語言硬規則(M6 / quick 用):字幕常為簡體,產出必須是繁體 zh-TW。
_ZH_TW_RULE = ("輸出語言:整篇文章一律繁體中文(台灣用語)。原文即使是簡體,"
               "也必須逐字轉為繁體——這是硬性要求,不可殘留簡體字。"
               "例外:程式碼、英文、數字、專有代號保留原樣,不做繁簡轉換。")

_NOTE_SCHEMA = """{
  "segment_id": %d,
  "time_range": [%s, %s],
  "topic": "本段主題一句話",
  "points": [
    {"claim": "論點完整敘述", "timestamp": 0.0,
     "evidence_quote": "逐字稿原句(可截短)", "importance": 3, "confidence": "high"}
  ],
  "entities": ["工具名", "專有名詞"],
  "facts_numbers": [{"value": "數值原文", "context": "一句說明", "timestamp": 0.0}],
  "code_blocks": [{"lang": "語言", "code": "程式碼", "timestamp": 0.0, "note": "口述與畫面差異(若有)"}],
  "speaker_emphasis": ["講者明示重要的內容"]
}"""


def ts(sec: float) -> str:
    s = int(sec)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_sentences(sentences: list[dict]) -> str:
    return "\n".join(f"[{ts(s['start'])}] {s['text']}" for s in sentences)


def _meta_block(transcript: dict, extra: str = "") -> str:
    lines = [
        f"- 標題:{transcript['title']}",
        f"- 頻道:{transcript.get('uploader', '')}",
        f"- 時長:{ts(transcript['duration_sec'])}",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def m5_prompt(segment: dict, transcript: dict, type_code: str) -> str:
    asr = f"5. {_ASR_NOTE}\n" if transcript.get("source") == "auto_subs" else ""
    prefix = segment.get("context_prefix") or "(無)"
    schema = _NOTE_SCHEMA % (segment["segment_id"], segment["start"], segment["end"])
    return f"""你是逐字稿分析員,任務是「不遺漏地記錄」以下影片段落的所有內容。

## 影片資訊
{_meta_block(transcript, f"- 章節:{segment.get('chapter_title') or '(無)'}")}
- 本段時間範圍:{ts(segment['start'])}–{ts(segment['end'])}

## 前段脈絡(僅供理解,不需記錄)
{prefix}

## 本段逐字稿(每行開頭為時間戳)
{_format_sentences(segment['sentences'])}

## 任務要求
1. 寧可冗長,不可精簡——壓縮是後續階段的事。
2. 不得省略「看似次要」的論點;不確定的內容標 confidence: "low" 而不是丟棄。
3. 每個論點附時間戳(秒數,浮點數)與一句逐字稿原文依據(evidence_quote)。
4. 講者明示的重點(「這個很重要」「記下來」)收進 speaker_emphasis。
{asr}- 語言:topic / claim / context / speaker_emphasis 等你自己的敘述文字一律用繁體中文(台灣用語);但 evidence_quote、facts_numbers 的 value、code_blocks 的 code 必須保留逐字稿原文(可能是簡體),不做繁簡轉換。
{TYPE_RULES[type_code]}

## 輸出格式
只輸出一個合法 JSON 物件,不要任何其他文字。schema(含本段固定值):
{schema}
"""


def render_note_block(note: dict) -> str:
    lines = [f"### 段落 {note.get('segment_id')}:{note.get('topic', '')}"]
    tr = note.get("time_range")
    if tr:
        lines.append(f"時間範圍:{ts(tr[0])}–{ts(tr[1])}")
    for p in note.get("points", []):
        conf = "(confidence: low)" if p.get("confidence") == "low" else ""
        lines.append(f"- [{ts(p.get('timestamp', 0))}] {p.get('claim', '')}{conf}")
        if p.get("evidence_quote"):
            lines.append(f"  依據:「{p['evidence_quote']}」")
    if note.get("entities"):
        lines.append("工具/專有名詞:" + "、".join(note["entities"]))
    for f in note.get("facts_numbers", []):
        lines.append(f"- 數字:[{ts(f.get('timestamp', 0))}] {f.get('value', '')} — {f.get('context', '')}")
    for cb in note.get("code_blocks", []):
        lines.append(f"```{cb.get('lang', '')}\n{cb.get('code', '')}\n```")
        if cb.get("note"):
            lines.append(f"(註:{cb['note']})")
    if note.get("speaker_emphasis"):
        lines.append("講者強調:" + ";".join(note["speaker_emphasis"]))
    return "\n".join(lines)


def _failed_note(failed_segment_ids: list[int]) -> str:
    if not failed_segment_ids:
        return ""
    ids = "、".join(f"第 {i} 段" for i in failed_segment_ids)
    return f"\n注意:{ids}的筆記產生失敗,請在文章開頭以引言區塊註明該段內容缺漏。\n"


def m6_prompt(blocks: list[str], transcript: dict, type_code: str,
              failed_segment_ids: list[int]) -> str:
    joined = "\n\n---\n\n".join(blocks)
    return f"""你是技術寫作者。以下是一支影片各段落的詳細筆記,請整合成一篇結構完整的繁體中文文章。

**{_ZH_TW_RULE}**

## 影片資訊
{_meta_block(transcript)}

## 整合規則
1. 資訊留存為第一優先,可讀性第二;不得為了流暢而丟論點。
2. 相鄰段落因重疊造成的重複論點需合併,但不同角度的重述要保留。
3. 每個主要論點後附時間戳,格式 [mm:ss](超過一小時用 [h:mm:ss]),讓讀者可跳回原片。
4. 文章結構:開頭 TL;DR(5–8 條)→ 依主題重組的正文(不必然照影片順序)→ 附錄。
5. {_APPENDIX_RULES[type_code]}
6. 專有名詞保留原文;{TYPE_RULES[type_code]}
{_failed_note(failed_segment_ids)}
## 分段筆記
{joined}

只輸出文章 markdown,不要任何其他說明。
"""


def m6_mid_prompt(blocks: list[str], transcript: dict, type_code: str) -> str:
    joined = "\n\n---\n\n".join(blocks)
    return f"""以下是影片「{transcript['title']}」相鄰數段的詳細筆記。
請合併成一份「合併筆記」:去除重疊重複的論點、保留所有獨立論點與其時間戳。
{TYPE_RULES[type_code]}
輸出 markdown 條列(維持與輸入相同的格式),不要文章化,不得省略任何獨立論點。

{joined}
"""


def quick_prompt(transcript: dict, type_code: str) -> str:
    asr = f"\n4. {_ASR_NOTE}" if transcript.get("source") == "auto_subs" else ""
    return f"""你是逐字稿分析員兼技術寫作者。以下是一支短影片的完整逐字稿,請直接產出一篇繁體中文「重點文章」。

**{_ZH_TW_RULE}**

## 影片資訊
{_meta_block(transcript)}

## 逐字稿(每行開頭為時間戳)
{_format_sentences(transcript['sentences'])}

## 要求
1. 資訊留存為第一優先:不得省略「看似次要」的論點;數字、專有名詞、程式碼保留原文。
2. 文章結構:開頭 TL;DR(3–6 條)→ 依主題重組的正文,每個主要論點附 [mm:ss] 時間戳 → {_APPENDIX_RULES[type_code]}
3. {TYPE_RULES[type_code]}{asr}

只輸出文章 markdown,不要任何其他說明。
"""
