"""claude -p wrapper:整個專案唯一的 LLM 呼叫入口(design D5)。"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass

_CLI_BASE = ["claude", "-p", "--output-format", "json", "--tools", ""]

_REPAIR_PROMPT = (
    "下面這段輸出應該是合法 JSON,但解析失敗。"
    "請把它修成合法 JSON,只輸出修好的 JSON,不要任何說明文字:\n\n"
)


class LLMError(Exception):
    """claude -p 呼叫失敗(重試後仍失敗、或 JSON 修不回來)。"""


@dataclass
class LLMResult:
    text: str
    parsed: dict | list | None
    usage: dict
    cost_usd: float
    duration_sec: float
    model: str


def _extract_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[A-Za-z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[}\]]", t, re.S)
        if m is None:
            raise
        return json.loads(m.group(0))


def _merge_usage(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, (int, float)) and isinstance(out.get(k, 0), (int, float)):
            out[k] = out.get(k, 0) + v
    return out


def _invoke(prompt: str, model: str, timeout_sec: int, run):
    proc = run(
        _CLI_BASE + ["--model", model],
        input=prompt, capture_output=True, text=True, timeout=timeout_sec,
    )
    if proc.returncode != 0:
        raise LLMError(f"claude -p exit={proc.returncode}:{(proc.stderr or '')[-500:]}")
    data = json.loads(proc.stdout)
    if data.get("is_error"):
        raise LLMError(f"claude -p 回報錯誤:{str(data.get('result'))[:500]}")
    return data


def call_llm(
    prompt: str,
    model: str,
    expect_json: bool = False,
    *,
    timeout_sec: int = 1800,
    retries: int = 1,
    retry_wait_sec: int = 30,
    run=subprocess.run,
    sleep=time.sleep,
    on_retry=None,
) -> LLMResult:
    start = time.monotonic()
    attempt = 0
    while True:
        try:
            data = _invoke(prompt, model, timeout_sec, run)
            break
        except (LLMError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            attempt += 1
            if attempt > retries:
                raise LLMError(f"claude -p 重試後仍失敗:{e}") from e
            # 重試前先回報:等待期間(預設 30s)原本是完全靜默的,無從分辨卡死或重試。
            if on_retry is not None:
                on_retry(attempt, retries, retry_wait_sec, e)
            sleep(retry_wait_sec)

    text = data.get("result") or ""
    usage = data.get("usage") or {}
    cost = float(data.get("total_cost_usd") or 0.0)
    parsed = None

    if expect_json:
        try:
            parsed = _extract_json(text)
        except json.JSONDecodeError:
            try:
                repair = _invoke(_REPAIR_PROMPT + text, model, timeout_sec, run)
            except (LLMError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
                raise LLMError(f"JSON 修復呼叫失敗:{e}") from e
            usage = _merge_usage(usage, repair.get("usage") or {})
            cost += float(repair.get("total_cost_usd") or 0.0)
            text = repair.get("result") or ""
            try:
                parsed = _extract_json(text)
            except json.JSONDecodeError as e:
                raise LLMError("JSON 修復後仍解析失敗") from e

    return LLMResult(
        text=text, parsed=parsed, usage=usage, cost_usd=cost,
        duration_sec=time.monotonic() - start, model=model,
    )
