"""vault 整合:文章匯出 vault/raw/(原子寫入)。絕不寫 wiki/。"""
from __future__ import annotations

import datetime as dt
import os
import re
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
