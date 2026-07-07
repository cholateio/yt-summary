"""M1 擷取:yt-dlp metadata + 字幕下載(v1 只走字幕路徑,無 Whisper)。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

DEFAULT_LANG_PRIORITY = ["zh-TW", "zh-Hant", "zh", "en"]


class FetchError(Exception):
    """影片不可用 / 無字幕 / yt-dlp 失敗。"""


def fetch_meta(url: str, run=subprocess.run) -> dict:
    proc = run(
        ["yt-dlp", "--dump-json", "--no-download", "--no-playlist", url],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise FetchError(f"yt-dlp metadata 失敗:{(proc.stderr or '')[-500:]}")
    first_line = proc.stdout.strip().splitlines()[0]
    return json.loads(first_line)


def pick_subtitle_lang(meta: dict, priority=DEFAULT_LANG_PRIORITY):
    manual = meta.get("subtitles") or {}
    auto = meta.get("automatic_captions") or {}
    for lang in priority:
        if manual.get(lang):
            return lang, "manual_subs"
    for lang in priority:
        if auto.get(lang):
            return lang, "auto_subs"
    return None


def download_subtitle(url: str, lang: str, source: str, workdir: Path,
                      run=subprocess.run) -> Path:
    flag = "--write-subs" if source == "manual_subs" else "--write-auto-subs"
    proc = run(
        ["yt-dlp", "--skip-download", "--no-playlist", flag,
         "--sub-langs", lang, "--sub-format", "json3",
         "-o", str(Path(workdir) / "%(id)s.%(ext)s"), url],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise FetchError(f"yt-dlp 字幕下載失敗:{(proc.stderr or '')[-500:]}")
    candidates = sorted(Path(workdir).glob("*.json3"))
    if not candidates:
        raise FetchError("字幕檔下載後未找到(.json3)")
    return candidates[0]
