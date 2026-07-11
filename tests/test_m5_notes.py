from yt_summary.llm import LLMError, LLMResult
from yt_summary.m5_notes import map_segments

SEG = lambda i: {"segment_id": i, "start": i * 100.0, "end": i * 100.0 + 90,
                 "chapter_title": None, "context_prefix": "",
                 "sentences": [{"i": 0, "start": i * 100.0, "end": i * 100.0 + 4,
                                "text": "測試句"}],
                 "token_estimate": 3}

TRANSCRIPT = {"video_id": "v", "title": "T", "duration_sec": 400,
              "source": "manual_subs", "language": "zh-TW", "uploader": "",
              "upload_date": "", "webpage_url": "", "chapters": [],
              "sentences": []}


def _result(parsed):
    return LLMResult(text="", parsed=parsed, usage={"input_tokens": 1, "output_tokens": 1},
                     cost_usd=0.01, duration_sec=0.1, model="sonnet")


def test_map_success_and_ordering():
    def call(prompt, model, expect_json=False, **kw):
        # 從 prompt 的 schema 取回 segment_id(prompt 含 "segment_id": N)
        import re
        sid = int(re.search(r'"segment_id": (\d+)', prompt).group(1))
        return _result({"segment_id": sid, "topic": f"t{sid}", "points": []})

    notes, results = map_segments([SEG(1), SEG(0)], TRANSCRIPT, "A", "sonnet",
                                  concurrency=2, call=call)
    assert [n["segment_id"] for n in notes] == [0, 1]
    assert all(n["status"] == "ok" for n in notes)
    assert len(results) == 2


def test_map_partial_failure():
    def call(prompt, model, expect_json=False, **kw):
        if '"segment_id": 1' in prompt:
            raise LLMError("boom")
        return _result({"segment_id": 0, "topic": "t0", "points": []})

    notes, results = map_segments([SEG(0), SEG(1)], TRANSCRIPT, "A", "sonnet",
                                  concurrency=1, call=call)
    assert notes[0]["status"] == "ok"
    assert notes[1] == {"segment_id": 1, "status": "failed", "error": "boom"}
    assert len(results) == 1  # 失敗的呼叫沒有 LLMResult


def test_map_fills_missing_segment_id():
    def call(prompt, model, expect_json=False, **kw):
        return _result({"topic": "模型忘了填 id", "points": []})

    notes, _ = map_segments([SEG(5)], TRANSCRIPT, "A", "sonnet",
                            concurrency=1, call=call)
    assert notes[0]["segment_id"] == 5


def test_on_progress_reports_every_segment_including_failures():
    def call(prompt, model, expect_json=False, **kw):
        if '"segment_id": 1' in prompt:
            raise LLMError("boom")
        return _result({"segment_id": 0, "topic": "t0", "points": []})

    seen = []
    map_segments([SEG(0), SEG(1)], TRANSCRIPT, "A", "sonnet", concurrency=1,
                 call=call, on_progress=lambda *a: seen.append(a))

    # 單段失敗不中斷,但必須即時回報——否則使用者以為全數成功,實際少了一段
    assert [(done, total) for done, total, _, _ in seen] == [(1, 2), (2, 2)]
    assert {seg_id: err for _, _, seg_id, err in seen} == {0: None, 1: "boom"}
