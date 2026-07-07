from yt_summary.llm import LLMResult
from yt_summary.m6_reduce import reduce_notes

TRANSCRIPT = {"video_id": "v", "title": "T", "duration_sec": 400,
              "source": "manual_subs", "language": "zh-TW", "uploader": "",
              "upload_date": "", "webpage_url": "", "chapters": [], "sentences": []}


def _note(i):
    return {"segment_id": i, "status": "ok", "time_range": [0, 1],
            "topic": f"主題{i}", "points": [], "entities": [],
            "facts_numbers": [], "code_blocks": [], "speaker_emphasis": []}


def _result(text):
    return LLMResult(text=text, parsed=None, usage={"input_tokens": 1, "output_tokens": 1},
                     cost_usd=0.01, duration_sec=0.1, model="opus")


def test_single_reduce():
    calls = []

    def call(prompt, model, **kw):
        calls.append(prompt)
        return _result("# 文章")

    article, results = reduce_notes([_note(0), _note(1)], TRANSCRIPT, "A", "opus", call=call)
    assert article == "# 文章"
    assert len(calls) == 1
    assert "主題0" in calls[0] and "主題1" in calls[0]


def test_failed_segments_mentioned():
    captured = []

    def call(prompt, model, **kw):
        captured.append(prompt)
        return _result("# 文章")

    notes = [_note(0), {"segment_id": 1, "status": "failed", "error": "x"}]
    reduce_notes(notes, TRANSCRIPT, "A", "opus", call=call)
    assert "第 1 段" in captured[0]


def test_mid_reduce_when_over_threshold():
    calls = []

    def call(prompt, model, **kw):
        calls.append(prompt)
        return _result(f"合併稿{len(calls)}")

    # threshold=0 強制走中間 reduce;6 個 note、chunk 4 → 2 次 mid + 1 次 final
    notes = [_note(i) for i in range(6)]
    article, results = reduce_notes(notes, TRANSCRIPT, "A", "opus", call=call,
                                    mid_reduce_threshold=0, chunk_size=4)
    assert len(calls) == 3
    assert article == "合併稿3"
    assert "合併稿1" in calls[2] and "合併稿2" in calls[2]  # final 吃 mid 的輸出
    assert len(results) == 3
