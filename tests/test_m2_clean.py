import json

from yt_summary.m2_clean import (
    build_transcript, dedup_cues, parse_json3, split_sentences,
)


def _cue(start, end, text):
    return {"start": start, "end": end, "text": text}


def test_parse_json3(tmp_path):
    data = {"events": [
        {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "大家好"}]},
        {"tStartMs": 2000, "dDurationMs": 1500, "segs": [{"utf8": "今天"}, {"utf8": "聊聊"}]},
        {"tStartMs": 4000, "dDurationMs": 1000},  # 無 segs → 略過
    ]}
    p = tmp_path / "s.json3"
    p.write_text(json.dumps(data), encoding="utf-8")
    cues = parse_json3(p)
    assert cues == [_cue(0.0, 2.0, "大家好"), _cue(2.0, 3.5, "今天聊聊")]


def test_dedup_rolling_captions():
    cues = [
        _cue(0, 2, "今天我們要聊"),
        _cue(2, 4, "今天我們要聊 AI 工具"),   # 前綴重複
        _cue(4, 6, "AI 工具"),               # 完全被前句尾包含 → 丟棄
        _cue(6, 8, "的使用方式"),
    ]
    out = dedup_cues(cues)
    assert [c["text"] for c in out] == ["今天我們要聊", "AI 工具", "的使用方式"]


def test_split_on_gap():
    cues = [_cue(0, 1, "第一句沒有標點"), _cue(3, 4, "第二句")]  # gap 2s > 0.8
    sents = split_sentences(cues)
    assert len(sents) == 2
    assert sents[0]["text"] == "第一句沒有標點"
    assert sents[0]["start"] == 0 and sents[0]["end"] == 1
    assert sents[1]["i"] == 1


def test_split_on_punctuation():
    cues = [_cue(0, 1, "先講結論。"), _cue(1.2, 2, "再講原因")]
    sents = split_sentences(cues)
    assert [s["text"] for s in sents] == ["先講結論。", "再講原因"]


def test_ascii_join_inserts_space():
    cues = [_cue(0, 1, "we use"), _cue(1.1, 2, "pytest here")]
    sents = split_sentences(cues)
    assert sents[0]["text"] == "we use pytest here"


def test_build_transcript():
    meta = {"id": "abc", "title": "T", "duration": 100, "uploader": "U",
            "upload_date": "20260701", "webpage_url": "https://youtu.be/abc",
            "chapters": [{"title": "開場", "start_time": 0, "end_time": 50}]}
    sents = [{"i": 0, "start": 0.0, "end": 1.0, "text": "hi"}]
    t = build_transcript(meta, sents, "auto_subs", "zh-TW")
    assert t["video_id"] == "abc"
    assert t["duration_sec"] == 100
    assert t["source"] == "auto_subs"
    assert t["chapters"] == [{"title": "開場", "start": 0.0, "end": 50.0}]
    assert t["sentences"] == sents
