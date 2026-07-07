import json

from yt_summary import cli, m1_fetch, m5_notes, m6_reduce, quick


def test_decide_mode():
    assert cli.decide_mode(600, "auto", 900) == "quick"
    assert cli.decide_mode(1200, "auto", 900) == "full"
    assert cli.decide_mode(900, "auto", 900) == "full"    # 邊界:>= threshold 走 full
    assert cli.decide_mode(1200, "quick", 900) == "quick"  # 強制覆寫
    assert cli.decide_mode(600, "full", 900) == "full"


CONFIG_TMPL = """\
defaults: {{ language_out: zh-TW, concurrency: 1, output_dir: {out} }}
modes: {{ quick_threshold_sec: 900 }}
llm:
  models: {{ m5: sonnet, m6: opus, quick: opus }}
vault: {{ export: true, raw_dir: {raw} }}
types:
  A: {{ segment_tokens: [3000, 4000], overlap_sec: 45 }}
"""


def _write_config(tmp_path):
    out = tmp_path / "output"
    raw = tmp_path / "raw"
    raw.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG_TMPL.format(out=out, raw=raw), encoding="utf-8")
    return cfg, out, raw


JSON3 = {"events": [{"tStartMs": 0, "dDurationMs": 3000, "segs": [{"utf8": "哈囉大家好。"}]}]}

META = {"id": "abcdefghijk", "title": "短片", "duration": 300,
        "uploader": "頻道", "upload_date": "20260701",
        "webpage_url": "https://youtu.be/abcdefghijk", "chapters": [],
        "subtitles": {}, "automatic_captions": {"zh-TW": [{"ext": "json3"}]}}


def test_run_quick_end_to_end(tmp_path, monkeypatch):
    cfg, out, raw = _write_config(tmp_path)

    monkeypatch.setattr(m1_fetch, "fetch_meta", lambda url, run=None: META)

    def fake_download(url, lang, source, workdir, run=None):
        p = workdir / "abcdefghijk.zh-TW.json3"
        p.write_text(json.dumps(JSON3), encoding="utf-8")
        return p

    monkeypatch.setattr(m1_fetch, "download_subtitle", fake_download)
    monkeypatch.setattr(quick, "quick_summarize",
                        lambda transcript, t, m, call=None: ("# 文章", []))

    rc = cli.main(["https://youtu.be/abcdefghijk", "--type", "A",
                   "--config", str(cfg)])
    assert rc == 0
    outdir = out / "abcdefghijk"
    assert (outdir / "article_final.md").read_text(encoding="utf-8") == "# 文章"
    assert (outdir / "transcript.json").exists()
    assert (outdir / "run.log").exists()
    exported = list(raw.glob("yt-*-abcdefghijk.md"))
    assert len(exported) == 1                      # vault 匯出
    assert "# 文章" in exported[0].read_text(encoding="utf-8")
    assert not (outdir / "segments.json").exists()      # quick 模式不產生 M3/M5 產物
    assert not (outdir / "segment_notes").exists()


META_FULL = {**META, "duration": 1200}


def test_run_full_end_to_end(tmp_path, monkeypatch, capsys):
    cfg, out, raw = _write_config(tmp_path)

    monkeypatch.setattr(m1_fetch, "fetch_meta", lambda url, run=None: META_FULL)

    def fake_download(url, lang, source, workdir, run=None):
        p = workdir / "abcdefghijk.zh-TW.json3"
        p.write_text(json.dumps(JSON3), encoding="utf-8")
        return p

    monkeypatch.setattr(m1_fetch, "download_subtitle", fake_download)

    def fake_map_segments(segments, transcript, type_code, model, concurrency, call=None):
        assert isinstance(segments, list) and len(segments) > 0
        assert model == "sonnet"
        assert concurrency == 1
        return ([{"segment_id": 0, "status": "ok", "topic": "t", "points": []},
                 {"segment_id": 1, "status": "failed", "error": "boom"}], [])

    def fake_reduce_notes(notes, transcript, type_code, model, call=None,
                          estimate=None, mid_reduce_threshold=60000, chunk_size=4):
        assert model == "opus"
        assert len(notes) == 2
        return ("# 長片文章", [])

    monkeypatch.setattr(m5_notes, "map_segments", fake_map_segments)
    monkeypatch.setattr(m6_reduce, "reduce_notes", fake_reduce_notes)

    rc = cli.main(["https://youtu.be/abcdefghijk", "--type", "A",
                   "--config", str(cfg)])
    assert rc == 0
    outdir = out / "abcdefghijk"
    assert (outdir / "article_final.md").read_text(encoding="utf-8") == "# 長片文章"

    segments_json = json.loads((outdir / "segments.json").read_text(encoding="utf-8"))
    assert len(segments_json["segments"]) > 0

    assert (outdir / "segment_notes" / "segment_000.json").exists()
    assert (outdir / "segment_notes" / "segment_001.json").exists()

    assert "1 failed" in (outdir / "run.log").read_text(encoding="utf-8")

    exported = list(raw.glob("yt-*-abcdefghijk.md"))
    assert len(exported) == 1
    assert "# 長片文章" in exported[0].read_text(encoding="utf-8")


def test_run_no_vault_flag(tmp_path, monkeypatch):
    cfg, out, raw = _write_config(tmp_path)
    monkeypatch.setattr(m1_fetch, "fetch_meta", lambda url, run=None: META)

    def fake_download(url, lang, source, workdir, run=None):
        p = workdir / "abcdefghijk.zh-TW.json3"
        p.write_text(json.dumps(JSON3), encoding="utf-8")
        return p

    monkeypatch.setattr(m1_fetch, "download_subtitle", fake_download)
    monkeypatch.setattr(quick, "quick_summarize",
                        lambda transcript, t, m, call=None: ("# 文章", []))

    rc = cli.main(["https://youtu.be/abcdefghijk", "--type", "A",
                   "--config", str(cfg), "--no-vault"])
    assert rc == 0
    assert list(raw.glob("*.md")) == []


def test_run_fetch_error_exits_1(tmp_path, monkeypatch, capsys):
    cfg, _, _ = _write_config(tmp_path)

    def boom(url, run=None):
        raise m1_fetch.FetchError("影片不存在")

    monkeypatch.setattr(m1_fetch, "fetch_meta", boom)
    rc = cli.main(["https://youtu.be/abcdefghijk", "--type", "A",
                   "--config", str(cfg)])
    assert rc == 1
    assert "影片不存在" in capsys.readouterr().err


def test_remove_subcommand(tmp_path, monkeypatch, capsys):
    cfg, out, raw = _write_config(tmp_path)
    # wiki 目錄 = raw 的手足目錄(vault/wiki)
    (raw.parent / "wiki").mkdir(exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "abcdefghijk").mkdir()
    (raw / "yt-20260707-短片-abcdefghijk.md").write_text("x", encoding="utf-8")

    rc = cli.main(["remove", "abcdefghijk", "--config", str(cfg)])
    assert rc == 0
    assert not (out / "abcdefghijk").exists()
    assert list(raw.glob("*.md")) == []
    assert "已完全移除" in capsys.readouterr().out
