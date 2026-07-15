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


# --- 原生軌優先(2026-07-15):翻譯字幕端點(tlang)被 YouTube 429 限流,
#     原生語言自動軌不受限且交給 LLM 翻譯品質更好 ---

def test_pick_native_auto_over_translated():
    # 英文影片:zh-Hant 只是機器翻譯軌,en 才是原生 ASR。改抓 en。
    meta = {"language": "en", "subtitles": {},
            "automatic_captions": {"zh-Hant": [{}], "en": [{}]}}
    assert pick_subtitle_lang(meta) == ("en", "auto_subs")


def test_pick_native_base_match_regional_code():
    # meta language 精確碼在 auto 中不存在時,退到 <base>-orig 原始軌。
    meta = {"language": "en", "subtitles": {},
            "automatic_captions": {"zh-Hant": [{}], "en-orig": [{}]}}
    assert pick_subtitle_lang(meta) == ("en-orig", "auto_subs")


def test_pick_native_orig_over_same_base_translated():
    # en-US 影片:同語系存在翻譯地區軌 en-GB 與原始軌 en-orig,必須選原始軌,
    # 不可因 dict 順序誤選翻譯軌(那又是被限流的 tlang 端點)。
    meta = {"language": "en-US", "subtitles": {},
            "automatic_captions": {"en-GB": [{}], "en-orig": [{}], "zh-Hant": [{}]}}
    assert pick_subtitle_lang(meta) == ("en-orig", "auto_subs")


def test_pick_skips_empty_native_track():
    # YouTube 偶爾列出語言鍵但無實體(空 list);不可回傳空軌,應跳過。
    meta = {"language": "en", "subtitles": {},
            "automatic_captions": {"en-US": [], "zh-Hant": [{}]}}
    assert pick_subtitle_lang(meta) == ("zh-Hant", "auto_subs")


def test_pick_manual_still_wins_over_native():
    # 人工字幕永遠最優先,即使影片原生語言是 en。
    meta = {"language": "en", "subtitles": {"zh-TW": [{}]},
            "automatic_captions": {"en": [{}], "zh-Hant": [{}]}}
    assert pick_subtitle_lang(meta) == ("zh-TW", "manual_subs")


def test_pick_chinese_video_prefers_native_asr():
    # 中文影片:原生 zh-Hant ASR 優於 zh-TW 翻譯軌(opencc 仍會繁化)。
    meta = {"language": "zh-Hant", "subtitles": {},
            "automatic_captions": {"zh-TW": [{}], "zh-Hant": [{}], "en": [{}]}}
    assert pick_subtitle_lang(meta) == ("zh-Hant", "auto_subs")


def test_pick_falls_back_to_priority_when_no_language():
    # 無 language 欄位(退化 metadata):維持原優先序,向後相容。
    meta = {"subtitles": {}, "automatic_captions": {"en": [{}], "zh-TW": [{}]}}
    assert pick_subtitle_lang(meta) == ("zh-TW", "auto_subs")


def test_download_subtitle_retries_on_429(tmp_path):
    sub = tmp_path / "abcdefghijk.zh-Hant.json3"
    sleeps = []
    n = {"i": 0}

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        n["i"] += 1
        if n["i"] < 3:  # 前兩次 429,第三次成功
            return subprocess.CompletedProcess(
                cmd, 1, stdout="", stderr="ERROR: HTTP Error 429: Too Many Requests")
        sub.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    path = download_subtitle("u", "zh-Hant", "auto_subs", tmp_path,
                             run=run, sleep=sleeps.append)
    assert path == sub
    assert n["i"] == 3
    assert sleeps == [1, 2]  # 指數退避,且成功後不再 sleep


def test_download_subtitle_detects_429_beyond_500_chars(tmp_path):
    # 429 被 yt-dlp 多行 warning 擠到 stderr 前段(末 500 字外)時仍須觸發退避。
    sub = tmp_path / "abcdefghijk.zh-Hant.json3"
    sleeps = []
    n = {"i": 0}
    long_warn = "HTTP Error 429: Too Many Requests\n" + ("WARNING padding\n" * 60)

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        n["i"] += 1
        if n["i"] < 2:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=long_warn)
        sub.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    assert len(long_warn) > 500 and "429" not in long_warn[-500:]
    path = download_subtitle("u", "zh-Hant", "auto_subs", tmp_path,
                             run=run, sleep=sleeps.append)
    assert path == sub
    assert sleeps == [1]  # 有偵測到 429 並退避一次


def test_download_subtitle_429_exhausted_raises(tmp_path):
    sleeps = []
    run = _run_factory([(1, "", "HTTP Error 429: Too Many Requests")] * 4)
    with pytest.raises(FetchError, match="429"):
        download_subtitle("u", "zh-Hant", "auto_subs", tmp_path,
                          run=run, sleep=sleeps.append, retries=4)
    assert len(run.calls) == 4  # 用滿 retries


def test_download_subtitle_no_retry_on_non_429(tmp_path):
    sleeps = []
    run = _run_factory([(1, "", "ERROR: Video unavailable")])
    with pytest.raises(FetchError, match="Video unavailable"):
        download_subtitle("u", "zh-TW", "manual_subs", tmp_path,
                          run=run, sleep=sleeps.append)
    assert len(run.calls) == 1  # 非 429 不重試
    assert sleeps == []


def test_download_subtitle_exhausted_429_message_keeps_marker(tmp_path):
    # 429 在 stderr 前段(末 500 字外)且重試耗盡:拋出的訊息仍須帶 429 線索。
    buried = "HTTP Error 429: Too Many Requests\n" + ("padding line\n" * 60)
    run = _run_factory([(1, "", buried)] * 3)
    with pytest.raises(FetchError, match="429"):
        download_subtitle("u", "zh-Hant", "auto_subs", tmp_path,
                          run=run, sleep=lambda s: None, retries=3)


def test_download_subtitle_unrelated_429_not_treated_as_ratelimit(tmp_path):
    # 裸 "429" 出現在無關脈絡(如格式代號)不可誤判為限流而重試。
    sleeps = []
    noise = ("WARNING: format 429 unavailable\n" + ("x" * 600)
             + "\nERROR: Video unavailable")
    run = _run_factory([(1, "", noise)])
    with pytest.raises(FetchError, match="Video unavailable"):
        download_subtitle("u", "zh-Hant", "auto_subs", tmp_path,
                          run=run, sleep=sleeps.append)
    assert len(run.calls) == 1  # 不重試
    assert sleeps == []
