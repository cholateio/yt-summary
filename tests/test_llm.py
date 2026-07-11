import json
import subprocess

import pytest

from yt_summary.llm import LLMError, call_llm


def _envelope(result_text, cost=0.01, is_error=False):
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": is_error,
        "result": result_text, "total_cost_usd": cost,
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
                  "cache_read_input_tokens": 0, "output_tokens": 7},
    })


def _fake_run(responses):
    """responses: list of (returncode, stdout, stderr);依呼叫次序回傳。"""
    calls = []

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        calls.append({"cmd": cmd, "input": input})
        rc, out, err = responses[len(calls) - 1]
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)

    run.calls = calls
    return run


def test_plain_text_success():
    run = _fake_run([(0, _envelope("答案文字"), "")])
    r = call_llm("問題", model="sonnet", run=run)
    assert r.text == "答案文字"
    assert r.parsed is None
    assert r.cost_usd == 0.01
    assert r.usage["output_tokens"] == 7
    assert r.model == "sonnet"
    # prompt 走 stdin,cmd 含 --model 與 --tools ""
    assert run.calls[0]["input"] == "問題"
    assert "--model" in run.calls[0]["cmd"] and "sonnet" in run.calls[0]["cmd"]
    assert "--tools" in run.calls[0]["cmd"]


def test_expect_json_with_fence():
    run = _fake_run([(0, _envelope('```json\n{"a": 1}\n```'), "")])
    r = call_llm("p", model="sonnet", expect_json=True, run=run)
    assert r.parsed == {"a": 1}


def test_expect_json_repair_retry():
    run = _fake_run([
        (0, _envelope('{"a": 1,,}'), ""),      # 壞 JSON
        (0, _envelope('{"a": 1}', cost=0.02), ""),  # 修復成功
    ])
    r = call_llm("p", model="sonnet", expect_json=True, run=run)
    assert r.parsed == {"a": 1}
    assert len(run.calls) == 2
    assert "修" in run.calls[1]["input"] or "JSON" in run.calls[1]["input"]
    assert r.cost_usd == pytest.approx(0.03)  # 兩次呼叫成本合併
    assert r.usage["input_tokens"] == 20      # usage 合併


def test_expect_json_repair_fails():
    run = _fake_run([(0, _envelope("不是 json"), ""), (0, _envelope("還是不是"), "")])
    with pytest.raises(LLMError):
        call_llm("p", model="sonnet", expect_json=True, run=run)


def test_nonzero_exit_retries_then_succeeds():
    slept = []
    run = _fake_run([(1, "", "boom"), (0, _envelope("ok"), "")])
    r = call_llm("p", model="opus", run=run, sleep=slept.append, retry_wait_sec=30)
    assert r.text == "ok"
    assert slept == [30]


def test_nonzero_exit_exhausts_retries():
    run = _fake_run([(1, "", "boom"), (1, "", "boom")])
    with pytest.raises(LLMError):
        call_llm("p", model="opus", run=run, sleep=lambda s: None)


def test_on_retry_is_called_before_the_silent_wait():
    run = _fake_run([(1, "", "rate limited"), (0, _envelope("ok"), "")])
    seen = []
    r = call_llm("p", model="opus", run=run, sleep=lambda s: None,
                 on_retry=lambda a, retries, wait, err: seen.append((a, retries, wait)))
    assert r.text == "ok"
    assert seen == [(1, 1, 30)]   # 重試前先出聲:30s 的等待原本完全靜默
    assert len(run.calls) == 2


def test_on_retry_not_called_when_first_attempt_succeeds():
    run = _fake_run([(0, _envelope("ok"), "")])
    seen = []
    call_llm("p", model="opus", run=run, on_retry=lambda *a: seen.append(a))
    assert seen == []
