from yt_summary.tokens import estimate_tokens


def test_pure_cjk():
    assert estimate_tokens("你好世界") == 4


def test_pure_english():
    # 2 詞 × 1.3 = 2.6 → round = 3
    assert estimate_tokens("hello world") == 3


def test_mixed():
    # 4 CJK + 1 詞 ×1.3 = 5.3 → 5
    assert estimate_tokens("我們使用 pytest") == 5


def test_empty_and_whitespace():
    assert estimate_tokens("") == 0
    assert estimate_tokens("   \n") == 0
