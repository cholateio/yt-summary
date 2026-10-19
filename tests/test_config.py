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
  raw_dir: /fake/vault/raw
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
    assert cfg.vault_raw_dir == Path("/fake/vault/raw")
    assert cfg.types["A"].segment_tokens == (3000, 4000)
    assert cfg.types["C"].overlap_sec == 30.0


def test_local_override_deep_merges(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(CONFIG_YAML, encoding="utf-8")
    (tmp_path / "config.local.yaml").write_text(
        "vault:\n  raw_dir: /other/vault/raw\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.vault_raw_dir == Path("/other/vault/raw")
    assert cfg.vault_export is True          # sibling keys survive the merge
    assert cfg.quick_threshold_sec == 900


def test_raw_dir_unset_is_none_and_tilde_expands(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text(CONFIG_YAML.replace("  raw_dir: /fake/vault/raw\n", ""), encoding="utf-8")
    assert load_config(p).vault_raw_dir is None

    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "config.local.yaml").write_text(
        "vault:\n  raw_dir: ~/vault/raw\n", encoding="utf-8")
    assert load_config(p).vault_raw_dir == tmp_path / "vault" / "raw"
