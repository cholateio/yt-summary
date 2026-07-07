from yt_summary.convert import to_traditional, to_traditional_markdown


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


def test_markdown_preserves_fenced_code():
    md = '正文数据说明\n```python\nprint("数据库")  # 优化\n```\n结尾'
    out = to_traditional_markdown(md)
    assert "正文資料說明" in out              # code 外:数据说明→資料說明
    assert 'print("数据库")  # 优化' in out   # code 內:簡體原樣保留(不改壞原始碼)
    assert "結尾" in out                       # code 後:结尾→結尾


def test_markdown_preserves_tilde_fenced_code():
    md = "正文数据\n~~~python\nx = \"数据库\"  # 优化\n~~~\n结尾"
    out = to_traditional_markdown(md)
    assert "正文資料" in out                    # code 外轉繁
    assert 'x = "数据库"  # 优化' in out         # tilde fence 內原樣保留
    assert "結尾" in out


def test_markdown_preserves_inline_code():
    md = "用 `数据库连接` 这个变量"
    out = to_traditional_markdown(md)
    assert "`数据库连接`" in out               # inline code 原樣
    assert "這個" in out                       # code 外:这个→這個


def test_markdown_empty():
    assert to_traditional_markdown("") == ""
    assert to_traditional_markdown(None) is None
