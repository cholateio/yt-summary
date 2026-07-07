from pathlib import Path

from yt_summary.config import load_config

CONFIG_YAML = """\
defaults:
  language_out: zh-TW
  concurrency: 2
  output_dir: ./output
modes:
  quick_threshold_sec: 900
llm:
  backend: claude-cli
  models: { m5: sonnet, m6: opus, quick: opus }
vault:
  export: true
  raw_dir: /mnt/c/Users/micro/Documents/vault/raw
types:
  A: { segment_tokens: [3000, 4000], overlap_sec: 45 }
  B: { segment_tokens: [3000, 4000], overlap_sec: 45 }
  C: { segment_tokens: [2000, 3000], overlap_sec: 30 }
"""


def test_load_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(CONFIG_YAML, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.language_out == "zh-TW"
    assert cfg.concurrency == 2
    assert cfg.output_dir == Path("./output")
    assert cfg.quick_threshold_sec == 900
    assert cfg.llm_models == {"m5": "sonnet", "m6": "opus", "quick": "opus"}
    assert cfg.vault_export is True
    assert cfg.vault_raw_dir == Path("/mnt/c/Users/micro/Documents/vault/raw")
    assert cfg.types["A"].segment_tokens == (3000, 4000)
    assert cfg.types["C"].overlap_sec == 30.0
