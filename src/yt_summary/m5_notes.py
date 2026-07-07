"""M5 分段筆記(map):每段一次 LLM 呼叫,ThreadPoolExecutor 並發。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import prompts
from .llm import LLMError, LLMResult, call_llm


def map_segments(segments: list[dict], transcript: dict, type_code: str,
                 model: str, concurrency: int,
                 call=call_llm) -> tuple[list[dict], list[LLMResult]]:
    def one(seg: dict) -> tuple[dict, LLMResult | None]:
        prompt = prompts.m5_prompt(seg, transcript, type_code)
        try:
            r = call(prompt, model=model, expect_json=True)
            note = r.parsed if isinstance(r.parsed, dict) else {"points": r.parsed or []}
            note["segment_id"] = note.get("segment_id", seg["segment_id"])
            note["status"] = "ok"
            return note, r
        except LLMError as e:
            return {"segment_id": seg["segment_id"], "status": "failed",
                    "error": str(e)}, None

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        pairs = list(ex.map(one, segments))

    notes = sorted((n for n, _ in pairs), key=lambda n: n["segment_id"])
    results = [r for _, r in pairs if r is not None]
    return notes, results
