"""M6 整合(reduce):筆記 → 文章;超量時先做中間 reduce(spec §M6)。"""
from __future__ import annotations

from . import prompts
from .llm import LLMResult, call_llm
from .tokens import estimate_tokens


def reduce_notes(notes: list[dict], transcript: dict, type_code: str, model: str,
                 call=call_llm, estimate=estimate_tokens,
                 mid_reduce_threshold: int = 60000,
                 chunk_size: int = 4) -> tuple[str, list[LLMResult]]:
    ok = sorted((n for n in notes if n.get("status") == "ok"),
                key=lambda n: n["segment_id"])
    failed_ids = sorted(n["segment_id"] for n in notes if n.get("status") != "ok")
    blocks = [prompts.render_note_block(n) for n in ok]
    results: list[LLMResult] = []

    if estimate("\n".join(blocks)) > mid_reduce_threshold:
        merged: list[str] = []
        for i in range(0, len(blocks), chunk_size):
            r = call(prompts.m6_mid_prompt(blocks[i:i + chunk_size], transcript, type_code),
                     model=model)
            merged.append(r.text)
            results.append(r)
        blocks = merged

    r = call(prompts.m6_prompt(blocks, transcript, type_code, failed_ids), model=model)
    results.append(r)
    return r.text, results
