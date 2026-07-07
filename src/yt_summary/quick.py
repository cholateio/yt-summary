"""quick 模式:短片全逐字稿 + super prompt 單次呼叫(design D1–D3)。"""
from __future__ import annotations

from . import prompts
from .llm import LLMResult, call_llm


def quick_summarize(transcript: dict, type_code: str, model: str,
                    call=call_llm) -> tuple[str, list[LLMResult]]:
    r = call(prompts.quick_prompt(transcript, type_code), model=model)
    return r.text, [r]
