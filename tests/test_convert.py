from yt_summary.convert import to_traditional


def test_simplified_to_traditional_taiwan():
    assert to_traditional("我换了思路") == "我換了思路"
    # s2twp 用台灣詞彙:数据库优化 → 資料庫最佳化
    assert to_traditional("数据库优化") == "資料庫最佳化"


def test_english_untouched():
    assert to_traditional("use Codex and KVcache") == "use Codex and KVcache"


def test_already_traditional_is_noop():
    assert to_traditional("我換了思路") == "我換了思路"


def test_empty_and_none():
    assert to_traditional("") == ""
    assert to_traditional(None) is None
