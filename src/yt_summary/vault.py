"""vault 整合:文章匯出 vault/raw/(原子寫入)。絕不寫 wiki/。"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .prompts import ts

_HOSTILE = re.compile(r'[\\/:*?"<>|#\[\]{}\s]+')


def slugify(title: str, max_len: int = 40) -> str:
    s = _HOSTILE.sub("-", title).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def _header(transcript: dict, type_code: str, generated: dt.date) -> str:
    return (
        f"# {transcript['title']}\n\n"
        f"> 來源:{transcript['webpage_url']}\n"
        f"> 頻道:{transcript.get('uploader', '')}|時長:{ts(transcript['duration_sec'])}"
        f"|type {type_code}\n"
        f"> 由 yt-summary 產生於 {generated.isoformat()}\n\n---\n\n"
    )


def export_article(article_md: str, transcript: dict, raw_dir: Path,
                   type_code: str, today: dt.date | None = None) -> Path:
    raw_dir = Path(raw_dir)

    # 清掃上次崩潰留下的暫存孤兒:write_text 與 os.replace 之間若中斷,
    # .tmp-* 會殘留,且可能被 ingest 的 *.md glob 誤撿——落地前先掃乾淨。
    for orphan in raw_dir.glob(".tmp-*"):
        orphan.unlink()

    generated = today or dt.date.today()
    vid = transcript["video_id"]
    name = f"yt-{generated.strftime('%Y%m%d')}-{slugify(transcript['title'])}-{vid}.md"

    content = _header(transcript, type_code, generated) + article_md
    tmp = raw_dir / f".tmp-{name}"
    target = raw_dir / name
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)  # 原子:ingest 只會看到完整檔或沒有檔

    # 重跑覆蓋語意:新檔成功落地「之後」才清同 video_id 的舊檔(檔名日期可能不同)。
    # 順序不可倒過來——先刪再寫的話,中斷會讓舊匯出消失且新檔沒落地。
    for stale in raw_dir.glob(f"yt-*-{vid}.md"):
        if stale != target:
            stale.unlink()
    return target


_ID = r"[A-Za-z0-9_-]{11}"
_URL_PATTERNS = [
    re.compile(r"[?&]v=(" + _ID + ")"),
    re.compile(r"youtu\.be/(" + _ID + ")"),
    re.compile(r"/(?:shorts|live|embed)/(" + _ID + ")"),
]


def extract_video_id(target: str) -> str:
    for pat in _URL_PATTERNS:
        m = pat.search(target)
        if m:
            return m.group(1)
    if re.fullmatch(_ID, target):
        return target
    raise ValueError(f"無法從輸入解析 YouTube video id:{target}")


@dataclass
class RemoveReport:
    video_id: str
    removed_output: bool
    removed_raw: list[str]
    affected_wiki: list[str]


def remove(target: str, output_dir: Path, raw_dir: Path,
           wiki_dir: Path) -> RemoveReport:
    vid = extract_video_id(target)

    removed_output = False
    out = Path(output_dir) / vid
    if out.exists():
        shutil.rmtree(out)
        removed_output = True

    removed_raw = []
    for f in Path(raw_dir).glob(f"yt-*-{vid}.md"):
        f.unlink()
        removed_raw.append(f.name)

    affected = []
    wiki_dir = Path(wiki_dir)
    for f in wiki_dir.rglob("*.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith("source:") and vid in line:
                affected.append(str(f.relative_to(wiki_dir)))
                break
    return RemoveReport(vid, removed_output, sorted(removed_raw), sorted(affected))
