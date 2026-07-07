"""M2 前處理:json3 解析、滾動字幕去重、規則法斷句、transcript 組裝。"""
from __future__ import annotations

import json
from pathlib import Path

_SENT_END = "。!?!?;;"


def parse_json3(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cues = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000.0
        end = start + ev.get("dDurationMs", 0) / 1000.0
        cues.append({"start": start, "end": end, "text": text})
    return cues


def _longest_overlap(a: str, b: str) -> int:
    for k in range(min(len(a), len(b)), 0, -1):
        if a[-k:] == b[:k]:
            return k
    return 0


def dedup_cues(cues: list[dict]) -> list[dict]:
    out: list[dict] = []
    for cue in cues:
        text = cue["text"]
        if out:
            k = _longest_overlap(out[-1]["text"], text)
            text = text[k:].strip()
            if not text:
                continue
        out.append({**cue, "text": text})
    return out


def _join(parts: list[str]) -> str:
    buf = ""
    for p in parts:
        if buf and buf[-1].isascii() and buf[-1].isalnum() \
                and p and p[0].isascii() and p[0].isalnum():
            buf += " "
        buf += p
    return buf.strip()


def split_sentences(cues: list[dict], gap_sec: float = 0.8,
                    max_chars: int = 120) -> list[dict]:
    sentences: list[dict] = []
    parts: list[str] = []
    buf_start = buf_end = 0.0

    def flush():
        nonlocal parts
        text = _join(parts)
        if text:
            sentences.append({"i": len(sentences), "start": buf_start,
                              "end": buf_end, "text": text})
        parts = []

    for cue in cues:
        if parts and cue["start"] - buf_end > gap_sec:
            flush()
        if not parts:
            buf_start = cue["start"]
        parts.append(cue["text"])
        buf_end = cue["end"]
        joined = _join(parts)
        if joined and (joined[-1] in _SENT_END or len(joined) >= max_chars):
            flush()
    flush()
    return sentences


def build_transcript(meta: dict, sentences: list[dict], source: str,
                     language: str) -> dict:
    chapters = [
        {"title": c.get("title", ""), "start": float(c.get("start_time") or 0),
         "end": float(c.get("end_time") or 0)}
        for c in (meta.get("chapters") or [])
    ]
    return {
        "video_id": meta["id"],
        "title": meta.get("title", ""),
        "duration_sec": int(meta.get("duration") or 0),
        "source": source,
        "language": language,
        "uploader": meta.get("uploader", ""),
        "upload_date": meta.get("upload_date", ""),
        "webpage_url": meta.get("webpage_url", ""),
        "chapters": chapters,
        "sentences": sentences,
    }
