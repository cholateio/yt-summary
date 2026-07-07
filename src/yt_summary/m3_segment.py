"""M3 切分:章節優先,否則 token 窗;overlap 以 context_prefix 附帶。"""
from __future__ import annotations

import re

from .tokens import estimate_tokens

GENERIC_CHAPTER = re.compile(
    r"^\s*(part|chapter|section|ep|episode|第?\s*[0-9一二三四五六七八九十]+\s*(部分|章|節|集)?)\s*[0-9]*\s*$",
    re.IGNORECASE,
)


def chapters_meaningful(chapters: list[dict]) -> bool:
    if not chapters:
        return False
    generic = sum(1 for c in chapters if GENERIC_CHAPTER.match(c.get("title") or ""))
    return generic <= len(chapters) / 2


def _window(sentences: list[dict], hi: int, estimate) -> list[list[dict]]:
    """token 窗切分,邊界對齊句尾。"""
    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_tokens = 0
    for s in sentences:
        t = estimate(s["text"])
        if cur and cur_tokens + t > hi:
            groups.append(cur)
            cur, cur_tokens = [], 0
        cur.append(s)
        cur_tokens += t
    if cur:
        groups.append(cur)
    return groups


def _by_chapters(chapters: list[dict], sentences: list[dict]) -> list[tuple[str, list[dict]]]:
    buckets: list[tuple[str, list[dict]]] = [(c["title"], []) for c in chapters]
    starts = [c["start"] for c in chapters]
    for s in sentences:
        idx = 0
        for j, st in enumerate(starts):
            if s["start"] >= st:
                idx = j
        buckets[idx][1].append(s)
    return [(t, g) for t, g in buckets if g]


def segment(transcript: dict, segment_tokens: tuple[int, int], overlap_sec: float,
            min_chapter_tokens: int = 800, estimate=estimate_tokens) -> list[dict]:
    lo, hi = segment_tokens
    sents = transcript["sentences"]
    if not sents:
        return []

    if chapters_meaningful(transcript.get("chapters") or []):
        buckets = _by_chapters(transcript["chapters"], sents)
        merged: list[tuple[str, list[dict]]] = []
        for title, group in buckets:
            tok = sum(estimate(s["text"]) for s in group)
            if tok < min_chapter_tokens and merged:
                merged[-1] = (merged[-1][0], merged[-1][1] + group)
            elif tok < min_chapter_tokens and not merged:
                merged.append((title, list(group)))  # 首章太小:先收,待下章合併
            else:
                if merged and sum(estimate(s["text"]) for s in merged[-1][1]) < min_chapter_tokens:
                    merged[-1] = (title, merged[-1][1] + list(group))  # 前章太小併入本章
                else:
                    merged.append((title, list(group)))
        groups = [(title, g) for title, group in merged
                  for g in _window(group, hi, estimate)]
    else:
        groups = [(None, g) for g in _window(sents, hi, estimate)]

    segments = []
    for idx, (title, group) in enumerate(groups):
        start, end = group[0]["start"], group[-1]["end"]
        prefix = ""
        if idx > 0:
            prefix_sents = [s for s in sents if start - overlap_sec <= s["start"] < start]
            prefix = " ".join(s["text"] for s in prefix_sents)
        segments.append({
            "segment_id": idx,
            "start": start,
            "end": end,
            "chapter_title": title,
            "context_prefix": prefix,
            "sentences": group,
            "token_estimate": sum(estimate(s["text"]) for s in group),
        })
    return segments
