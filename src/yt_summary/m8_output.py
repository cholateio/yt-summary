"""M8 輸出:中間產物落地 + run.log(耗時、token、成本彙總)。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LLMResult


@dataclass
class LogEntry:
    step: str
    duration_sec: float
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    note: str = ""


@dataclass
class RunLog:
    entries: list[LogEntry] = field(default_factory=list)

    def add(self, step: str, duration_sec: float, note: str = "") -> None:
        self.entries.append(LogEntry(step, duration_sec, note=note))

    def add_llm(self, step: str, duration_sec: float,
                results: list[LLMResult], note: str = "") -> None:
        tin = sum(
            r.usage.get("input_tokens", 0)
            + r.usage.get("cache_creation_input_tokens", 0)
            + r.usage.get("cache_read_input_tokens", 0)
            for r in results
        )
        tout = sum(r.usage.get("output_tokens", 0) for r in results)
        cost = sum(r.cost_usd for r in results)
        self.entries.append(
            LogEntry(step, duration_sec, len(results), tin, tout, cost, note)
        )

    def totals(self) -> tuple[float, int, int, float]:
        """回傳 (總耗時秒, 總輸入 token, 總輸出 token, 總成本 USD)。"""
        return (
            sum(e.duration_sec for e in self.entries),
            sum(e.tokens_in for e in self.entries),
            sum(e.tokens_out for e in self.entries),
            sum(e.cost_usd for e in self.entries),
        )

    def summary_line(self) -> str:
        """一行用量摘要,供 stdout 顯示(claude -p 訂閱制,成本為等值 API 估算)。"""
        dur, tin, tout, cost = self.totals()
        return (f"本次用量:輸入 {tin:,} tokens、輸出 {tout:,} tokens、"
                f"等值成本 ${cost:.2f}、耗時 {dur:.1f}s")

    def render(self) -> str:
        lines = ["yt-summary run log", "=" * 64]
        for e in self.entries:
            row = f"{e.step:<16}{e.duration_sec:>9.1f}s"
            if e.calls:
                row += (f"  calls={e.calls} in={e.tokens_in} out={e.tokens_out}"
                        f" cost=${e.cost_usd:.2f}")
            if e.note:
                row += f"  ({e.note})"
            lines.append(row)
        lines.append("-" * 64)
        total_t, _, _, total_c = self.totals()
        lines.append(f"{'total':<16}{total_t:>9.1f}s  cost=${total_c:.2f}")
        return "\n".join(lines) + "\n"


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def write_outputs(outdir: Path, transcript=None, segments=None, notes=None,
                  article=None, runlog=None) -> None:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if transcript is not None:
        _dump(outdir / "transcript.json", transcript)
    if segments is not None:
        _dump(outdir / "segments.json", {"segments": segments})
    if notes is not None:
        notes_dir = outdir / "segment_notes"
        notes_dir.mkdir(exist_ok=True)
        for n in notes:
            _dump(notes_dir / f"segment_{n['segment_id']:03d}.json", n)
    if article is not None:
        (outdir / "article_final.md").write_text(article, encoding="utf-8")
    if runlog is not None:
        (outdir / "run.log").write_text(runlog.render(), encoding="utf-8")
