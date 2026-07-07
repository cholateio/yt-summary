from yt_summary import prompts

TRANSCRIPT = {
    "video_id": "v1", "title": "量化交易入門", "duration_sec": 700,
    "source": "auto_subs", "language": "zh-TW", "uploader": "頻道",
    "upload_date": "20260701", "webpage_url": "https://youtu.be/v1",
    "chapters": [],
    "sentences": [{"i": 0, "start": 0.0, "end": 4.0, "text": "年化 14.2% 的策略"}],
}

SEGMENT = {"segment_id": 2, "start": 612.0, "end": 1180.5,
           "chapter_title": "回測", "context_prefix": "前段講了均線。",
           "sentences": [{"i": 5, "start": 612.0, "end": 616.0, "text": "年化 14.2% 的策略"}],
           "token_estimate": 10}

NOTE = {"segment_id": 2, "status": "ok", "time_range": [612.0, 1180.5],
        "topic": "回測陷阱",
        "points": [{"claim": "過度擬合是主因", "timestamp": 645.2,
                    "evidence_quote": "原句", "importance": 3, "confidence": "low"}],
        "entities": ["backtrader"],
        "facts_numbers": [{"value": "年化 14.2%", "context": "策略績效", "timestamp": 700.1}],
        "code_blocks": [{"lang": "python", "code": "x = 1", "timestamp": 820.0, "note": ""}],
        "speaker_emphasis": ["這個很重要"]}


def test_ts_format():
    assert prompts.ts(65) == "1:05"
    assert prompts.ts(3661) == "1:01:01"


def test_m5_prompt_contains_essentials():
    p = prompts.m5_prompt(SEGMENT, TRANSCRIPT, "B")
    assert "[10:12]" in p                      # 時間戳行
    assert "前段講了均線。" in p                 # context_prefix
    assert "僅供理解" in p                      # prefix 指示
    assert "原樣抄錄" in p                      # Type B 規則
    assert '"segment_id": 2' in p              # schema 綁定段落 id
    assert "ASR" in p                          # auto_subs → 錯字推斷註記
    assert "confidence" in p
    assert "繁體中文" in p                       # 敘述文字轉繁
    assert "evidence_quote" in p and "保留逐字稿原文" in p  # 引文保留原文


def test_m5_prompt_type_a_no_number_rule():
    p = prompts.m5_prompt(SEGMENT, TRANSCRIPT, "A")
    assert "原樣抄錄" not in p
    assert "推理鏈" in p


def test_render_note_block():
    b = prompts.render_note_block(NOTE)
    assert "回測陷阱" in b
    assert "過度擬合是主因" in b
    assert "10:45" in b            # 645.2s → 10:45
    assert "年化 14.2%" in b
    assert "```python" in b
    assert "confidence: low" in b
    assert "這個很重要" in b


def test_m6_prompt():
    p = prompts.m6_prompt(["區塊一", "區塊二"], TRANSCRIPT, "B", failed_segment_ids=[3])
    assert "TL;DR" in p
    assert "數字彙整表" in p       # Type B 附錄
    assert "區塊一" in p and "區塊二" in p
    assert "第 3 段" in p          # 缺段警告
    assert "[mm:ss]" in p or "時間戳" in p
    assert "必須逐字轉為繁體" in p   # 簡轉繁硬規則


def test_quick_prompt():
    p = prompts.quick_prompt(TRANSCRIPT, "C")
    assert "年化 14.2% 的策略" in p     # 全逐字稿
    assert "[0:00]" in p
    assert "程式碼" in p               # Type C 規則
    assert "TL;DR" in p
    assert "必須逐字轉為繁體" in p       # 簡轉繁硬規則
