import pytest

from yt_summary.vault import RemoveReport, extract_video_id, remove


def test_extract_video_id_variants():
    vid = "abcdefghijk"
    assert extract_video_id(f"https://www.youtube.com/watch?v={vid}") == vid
    assert extract_video_id(f"https://youtu.be/{vid}?t=10") == vid
    assert extract_video_id(f"https://www.youtube.com/shorts/{vid}") == vid
    assert extract_video_id(vid) == vid
    # 注意:任何 11 碼 [A-Za-z0-9_-] 字串都是合法 id(如 "not-a-video"),
    # 所以無效案例要用長度不符的字串
    with pytest.raises(ValueError):
        extract_video_id("hello")


def _setup(tmp_path, vid="abcdefghijk", ingested=False):
    out = tmp_path / "output" / vid
    out.mkdir(parents=True)
    (out / "article_final.md").write_text("x", encoding="utf-8")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / f"yt-20260707-標題-{vid}.md").write_text("x", encoding="utf-8")
    wiki = tmp_path / "wiki"
    (wiki / "ai" / "concepts").mkdir(parents=True)
    if ingested:
        (wiki / "ai" / "concepts" / "某筆記.md").write_text(
            f"---\ntitle: 某筆記\nsource: https://youtu.be/{vid}\n---\n內容",
            encoding="utf-8")
    return tmp_path / "output", raw, wiki


def test_remove_before_ingest(tmp_path):
    output_dir, raw, wiki = _setup(tmp_path)
    report = remove("abcdefghijk", output_dir, raw, wiki)
    assert report.removed_output is True
    assert report.removed_raw == ["yt-20260707-標題-abcdefghijk.md"]
    assert report.affected_wiki == []
    assert not (output_dir / "abcdefghijk").exists()
    assert not list(raw.glob("*.md"))


def test_remove_after_ingest_lists_wiki(tmp_path):
    output_dir, raw, wiki = _setup(tmp_path, ingested=True)
    report = remove("https://youtu.be/abcdefghijk", output_dir, raw, wiki)
    assert report.affected_wiki == ["ai/concepts/某筆記.md"]
    # wiki 檔案本體不得被修改或刪除
    assert (wiki / "ai" / "concepts" / "某筆記.md").exists()


def test_remove_nothing_to_do(tmp_path):
    output_dir = tmp_path / "output"
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    for d in (output_dir, raw, wiki):
        d.mkdir()
    report = remove("abcdefghijk", output_dir, raw, wiki)
    assert report == RemoveReport("abcdefghijk", False, [], [])
