import json
import subprocess

import pytest

from yt_summary.m1_fetch import (
    FetchError, download_subtitle, fetch_meta, pick_subtitle_lang,
)


def _run_factory(responses):
    calls = []

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        calls.append(cmd)
        rc, out, err = responses[len(calls) - 1]
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)

    run.calls = calls
    return run


META = {"id": "abcdefghijk", "title": "測試影片", "duration": 600,
        "subtitles": {}, "automatic_captions": {"zh-TW": [{"ext": "json3"}]}}


def test_fetch_meta_ok():
    run = _run_factory([(0, json.dumps(META), "")])
    meta = fetch_meta("https://youtu.be/abcdefghijk", run=run)
    assert meta["id"] == "abcdefghijk"
    assert "--no-playlist" in run.calls[0]


def test_fetch_meta_failure_raises():
    run = _run_factory([(1, "", "ERROR: Video unavailable")])
    with pytest.raises(FetchError, match="Video unavailable"):
        fetch_meta("https://youtu.be/x", run=run)


def test_pick_manual_over_auto():
    meta = {"subtitles": {"en": [{}]}, "automatic_captions": {"zh-TW": [{}]}}
    assert pick_subtitle_lang(meta) == ("en", "manual_subs")


def test_pick_priority_order_within_auto():
    meta = {"subtitles": {}, "automatic_captions": {"en": [{}], "zh-TW": [{}]}}
    assert pick_subtitle_lang(meta) == ("zh-TW", "auto_subs")


def test_pick_none_when_no_subs():
    assert pick_subtitle_lang({"subtitles": {}, "automatic_captions": {}}) is None


def test_download_subtitle_finds_file(tmp_path):
    sub = tmp_path / "abcdefghijk.zh-TW.json3"

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        sub.write_text("{}", encoding="utf-8")
        assert "--write-auto-subs" in cmd  # auto_subs 用 auto 旗標
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    path = download_subtitle("u", "zh-TW", "auto_subs", tmp_path, run=run)
    assert path == sub


def test_download_subtitle_missing_file_raises(tmp_path):
    run = _run_factory([(0, "", "")])
    with pytest.raises(FetchError, match="未找到"):
        download_subtitle("u", "zh-TW", "manual_subs", tmp_path, run=run)


def test_download_subtitle_ignores_stale_other_language(tmp_path):
    # workdir 跨重跑持久化:先前一次留下的 en 舊檔不該被本次 zh-TW 撿走。
    stale = tmp_path / "abcdefghijk.en.json3"
    stale.write_text("{}", encoding="utf-8")
    fresh = tmp_path / "abcdefghijk.zh-TW.json3"

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        fresh.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    path = download_subtitle("u", "zh-TW", "manual_subs", tmp_path, run=run)
    assert path == fresh


def test_fetch_meta_empty_stdout_raises():
    run = _run_factory([(0, "", "")])
    with pytest.raises(FetchError, match="未回傳"):
        fetch_meta("https://youtu.be/x", run=run)
