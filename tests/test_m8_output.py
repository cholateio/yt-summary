import json

from yt_summary.llm import LLMResult
from yt_summary.m8_output import RunLog, write_outputs


def _result(cost=0.5):
    return LLMResult(text="x", parsed=None,
                     usage={"input_tokens": 100, "cache_creation_input_tokens": 50,
                            "cache_read_input_tokens": 10, "output_tokens": 20},
                     cost_usd=cost, duration_sec=1.0, model="sonnet")


def test_runlog_render():
    log = RunLog()
    log.add("M1 擷取", 3.2)
    log.add_llm("M5 分段筆記", 100.0, [_result(), _result()], note="1 failed")
    out = log.render()
    assert "M1 擷取" in out
    assert "calls=2" in out
    assert "in=320" in out          # (100+50+10)×2
    assert "out=40" in out
    assert "cost=$1.00" in out
    assert "1 failed" in out
    assert "total" in out


def test_runlog_totals_and_summary():
    log = RunLog()
    log.add("M1 擷取", 3.0)
    # 兩次呼叫:每次 in=(100+50+10)=160、out=20、cost=0.5
    log.add_llm("M5 分段筆記", 100.0, [_result(), _result(cost=1500.0)])
    assert log.totals() == (103.0, 320, 40, 1500.5)
    s = log.summary_line()
    assert "320 tokens" in s          # 輸入
    assert "40 tokens" in s           # 輸出
    assert "$1500.50" in s            # 等值成本
    assert "103.0s" in s              # 耗時


def test_summary_line_thousands_separator():
    log = RunLog()
    log.add_llm("M6", 5.0, [LLMResult(
        text="x", parsed=None,
        usage={"input_tokens": 1234567, "output_tokens": 0},
        cost_usd=0.0, duration_sec=5.0, model="opus")])
    assert "1,234,567 tokens" in log.summary_line()


def test_write_outputs_full(tmp_path):
    log = RunLog()
    log.add("step", 1.0)
    write_outputs(
        tmp_path,
        transcript={"video_id": "v"},
        segments=[{"segment_id": 0}],
        notes=[{"segment_id": 0, "status": "ok"}],
        article="# 文章",
        runlog=log,
    )
    assert json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8")) == {"video_id": "v"}
    assert json.loads((tmp_path / "segments.json").read_text(encoding="utf-8")) == {"segments": [{"segment_id": 0}]}
    assert (tmp_path / "segment_notes" / "segment_000.json").exists()
    assert (tmp_path / "article_final.md").read_text(encoding="utf-8") == "# 文章"
    assert "step" in (tmp_path / "run.log").read_text(encoding="utf-8")


def test_write_outputs_quick_mode_partial(tmp_path):
    # quick 模式沒有 segments/notes → 不產生對應檔案
    write_outputs(tmp_path, transcript={"video_id": "v"}, article="# a")
    assert not (tmp_path / "segments.json").exists()
    assert not (tmp_path / "segment_notes").exists()
    assert (tmp_path / "article_final.md").exists()
