"""config.yaml 載入。只有 cli.py 使用;其他模組收明確參數。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TypeConfig:
    segment_tokens: tuple[int, int]
    overlap_sec: float


@dataclass(frozen=True)
class Config:
    language_out: str
    concurrency: int
    output_dir: Path
    quick_threshold_sec: int
    llm_models: dict[str, str]
    vault_export: bool
    vault_raw_dir: Path
    types: dict[str, TypeConfig]


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    d = raw.get("defaults", {})
    vault = raw.get("vault", {})
    types = {
        key: TypeConfig(
            segment_tokens=tuple(val["segment_tokens"]),
            overlap_sec=float(val["overlap_sec"]),
        )
        for key, val in raw.get("types", {}).items()
    }
    return Config(
        language_out=d.get("language_out", "zh-TW"),
        concurrency=int(d.get("concurrency", 2)),
        output_dir=Path(d.get("output_dir", "./output")),
        quick_threshold_sec=int(raw.get("modes", {}).get("quick_threshold_sec", 900)),
        llm_models=dict(
            raw.get("llm", {}).get("models", {"m5": "sonnet", "m6": "opus", "quick": "opus"})
        ),
        vault_export=bool(vault.get("export", True)),
        vault_raw_dir=Path(vault.get("raw_dir", "")),
        types=types,
    )
