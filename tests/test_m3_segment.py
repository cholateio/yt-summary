from yt_summary.m3_segment import chapters_meaningful, segment


def _sent(i, start, text):
    return {"i": i, "start": float(start), "end": float(start + 10), "text": text}


def _transcript(sentences, chapters=None):
    return {"video_id": "v", "title": "t", "duration_sec": 999999,
            "source": "auto_subs", "language": "zh-TW", "uploader": "",
            "upload_date": "", "webpage_url": "",
            "chapters": chapters or [], "sentences": sentences}


# 每句 20 CJK 字 ≈ 20 tokens,每句佔 10 秒
SENTS = [_sent(i, i * 10, "這是一句剛好二十個字的測試句子用來估算量" ) for i in range(100)]


def test_generic_chapters_detected():
    assert chapters_meaningful([{"title": "Part 1"}, {"title": "Part 2"}]) is False
    assert chapters_meaningful([{"title": "第 1 部分"}, {"title": "第 2 部分"}]) is False
    assert chapters_meaningful([{"title": "回測陷阱"}, {"title": "Part 2"}]) is True
    assert chapters_meaningful([]) is False


def test_token_window_split_no_chapters():
    segs = segment(_transcript(SENTS), (300, 400), overlap_sec=30)
    assert len(segs) >= 4
    for s in segs:
        assert s["token_estimate"] <= 400 + 20  # 邊界對齊句尾,允許最後一句溢出
    # 邊界必須落在句尾:每段句子連續且不重複
    all_ids = [x["i"] for s in segs for x in s["sentences"]]
    assert all_ids == list(range(100))


def test_overlap_context_prefix():
    segs = segment(_transcript(SENTS), (300, 400), overlap_sec=30)
    assert segs[0]["context_prefix"] == ""
    # 第二段的 prefix 應含前一段結尾 30 秒內(=3 句)的文字
    assert segs[1]["context_prefix"] != ""


def test_chapter_split_and_small_merge():
    chapters = [
        {"title": "開場", "start": 0.0, "end": 100.0},      # 10 句 ≈ 200 tokens < 800 → 併入下一章
        {"title": "主題一", "start": 100.0, "end": 600.0},
        {"title": "主題二", "start": 600.0, "end": 1000.0},
    ]
    segs = segment(_transcript(SENTS, chapters), (300, 400), overlap_sec=30)
    titles = {s["chapter_title"] for s in segs}
    assert "開場" not in titles          # 小章節被合併
    assert any(t for t in titles)


def test_empty_transcript():
    assert segment(_transcript([]), (300, 400), overlap_sec=30) == []
