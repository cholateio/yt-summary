import datetime as dt

from yt_summary.vault import export_article, slugify

TRANSCRIPT = {"video_id": "abcdefghijk", "title": "AI 工具:實戰/心得 #3",
              "duration_sec": 754, "source": "auto_subs", "language": "zh-TW",
              "uploader": "某頻道", "upload_date": "20260701",
              "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
              "chapters": [], "sentences": []}

TODAY = dt.date(2026, 7, 7)


def test_slugify_strips_hostile_chars():
    assert "/" not in slugify("AI 工具:實戰/心得 #3")
    assert " " not in slugify("a b c")
    assert slugify("") == "untitled"
    assert len(slugify("超" * 100)) <= 40


def test_export_writes_atomic_file(tmp_path):
    p = export_article("# 內文", TRANSCRIPT, tmp_path, "A", today=TODAY)
    assert p.parent == tmp_path
    assert p.name.startswith("yt-20260707-")
    assert p.name.endswith("-abcdefghijk.md")
    content = p.read_text(encoding="utf-8")
    assert "https://www.youtube.com/watch?v=abcdefghijk" in content  # 來源 URL(給 ingest 填 source)
    assert "某頻道" in content
    assert "12:34" in content       # 754s = 12:34
    assert "type A" in content
    assert "# 內文" in content
    assert not list(tmp_path.glob(".tmp-*"))  # 暫存檔已 rename 掉


def test_export_overwrites_stale_same_video(tmp_path):
    old = tmp_path / "yt-20260101-舊標題-abcdefghijk.md"
    old.write_text("舊", encoding="utf-8")
    p = export_article("# 新", TRANSCRIPT, tmp_path, "A", today=TODAY)
    assert not old.exists()          # 同 video_id 舊檔被清掉(重跑覆蓋語意)
    assert p.exists()
    assert len(list(tmp_path.glob("yt-*-abcdefghijk.md"))) == 1
