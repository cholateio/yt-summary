"""config.yaml 載入。只有 cli.py 使用;其他模組收明確參數。

A sibling `<stem>.local<suffix>` (e.g. config.local.yaml, gitignored) is
deep-merged over the base file; machine-specific values (vault.raw_dir) live there.
"""
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
    vault_raw_dir: Path | None  # None = not configured; never fall back to cwd
    types: dict[str, TypeConfig]


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def local_override_path(path: Path) -> Path:
    path = Path(path)
    return path.with_name(f"{path.stem}.local{path.suffix}")


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    local = local_override_path(path)
    if local.is_file():
        raw = _deep_merge(raw, yaml.safe_load(local.read_text(encoding="utf-8")) or {})
    d = raw.get("defaults", {})
    vault = raw.get("vault", {})
    raw_dir = vault.get("raw_dir")
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
        quick_threshold_sec=int(raw.get("modes", {}).get("quick_threshold_sec", 600)),
        llm_models=dict(
            raw.get("llm", {}).get("models", {"m5": "sonnet", "m6": "opus", "quick": "opus"})
        ),
        vault_export=bool(vault.get("export", True)),
        vault_raw_dir=Path(raw_dir).expanduser() if raw_dir else None,
        types=types,
    )
