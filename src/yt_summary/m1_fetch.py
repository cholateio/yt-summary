"""M1 擷取:yt-dlp metadata + 字幕下載(v1 只走字幕路徑,無 Whisper)。"""
from __future__ import annotations

import json
import subprocess
import time
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
    stdout = proc.stdout.strip()
    if not stdout:
        raise FetchError("yt-dlp 未回傳 metadata")
    first_line = stdout.splitlines()[0]
    return json.loads(first_line)


def pick_subtitle_lang(meta: dict, priority=DEFAULT_LANG_PRIORITY):
    manual = meta.get("subtitles") or {}
    auto = meta.get("automatic_captions") or {}
    # 1. 人工字幕(priority 序)——非機翻、最可靠。
    for lang in priority:
        if manual.get(lang):
            return lang, "manual_subs"
    # 2. 影片原生語言的自動軌。YouTube 對「自動翻譯」字幕端點(&tlang=)狠狠 429
    #    限流,原生語言 ASR 軌不走翻譯端點故不被限;且交給 LLM 翻譯(輸出固定
    #    zh-TW,見 prompts._ZH_TW_RULE)品質優於 YouTube 機翻。優先精確匹配
    #    meta['language'],否則同語系(base,如 en 對 en-orig)匹配。
    native = meta.get("language")
    if native:
        base = native.split("-")[0]
        # 只認「原生」候選:精確碼 > <base>-orig(YouTube 原始軌標記)> 純 base。
        # 不做寬鬆的同 base 掃描——那會誤選同語系的『翻譯』地區軌(如 en-US 影片
        # 撿到 en-GB 翻譯軌),反而踩回被限流的 tlang 端點。auto.get 的 truthy
        # 檢查避免回傳空軌(YouTube 偶有列出但無實體的語言鍵)。
        for cand in (native, f"{base}-orig", base):
            if auto.get(cand):
                return cand, "auto_subs"
    # 3. 翻譯自動軌(priority 序)——最後手段,端點會 429,靠 download_subtitle 退避。
    for lang in priority:
        if auto.get(lang):
            return lang, "auto_subs"
    return None


def download_subtitle(url: str, lang: str, source: str, workdir: Path,
                      run=subprocess.run, sleep=time.sleep, retries: int = 5) -> Path:
    flag = "--write-subs" if source == "manual_subs" else "--write-auto-subs"
    cmd = ["yt-dlp", "--skip-download", "--no-playlist", flag,
           "--sub-langs", lang, "--sub-format", "json3",
           "-o", str(Path(workdir) / "%(id)s.%(ext)s"), url]
    for attempt in range(max(1, retries)):
        proc = run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            break
        stderr = proc.stderr or ""
        # YouTube 翻譯字幕端點的 429 是間歇性 IP 限流,退避重試會過;yt-dlp 自身
        # --retries 不覆蓋字幕下載,故在此手動退避。其他錯誤(無字幕/影片不存在)
        # 是永久性的,即刻放棄不重試。用精確簽章比對(非裸 "429",那會誤中
        # "format 429 unavailable" 之類無關字串);掃完整 stderr——真正的 429 常被
        # yt-dlp 多行 warning(JS runtime / ffmpeg / impersonation)擠出末 500 字。
        is_429 = "HTTP Error 429" in stderr or "Too Many Requests" in stderr
        if is_429 and attempt < retries - 1:
            sleep(min(2 ** attempt, 30))  # 1,2,4,8,16… 上限 30s
            continue
        # 訊息截尾,但 429 標記另外前置——避免 429 被擠出末 500 字後診斷訊息失去線索。
        tag = "HTTP 429 重試耗盡;" if is_429 else ""
        raise FetchError(f"yt-dlp 字幕下載失敗:{tag}{stderr[-500:]}")
    # 只找本次要求語言的檔案:workdir 跨重跑持久化,不鎖語言的話 glob 可能
    # 撿到之前其他語言留下的舊檔(字母序早於本次新檔)。
    candidates = sorted(Path(workdir).glob(f"*.{lang}.json3"))
    if not candidates:
        raise FetchError("字幕檔下載後未找到(.json3)")
    return candidates[0]
