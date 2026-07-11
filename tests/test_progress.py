import io

from yt_summary.progress import Reporter


def _rep(**kw):
    buf = io.StringIO()
    return buf, Reporter(stream=buf, isatty=False, **kw)


def test_begin_then_numbered_steps():
    buf, rep = _rep()
    rep.begin("抓取影片資訊")
    rep.set_total(3)                 # 步數要抓到片長才知道 → 前導行不編號
    rep.ok("「片名」(9:59) → 模式 quick")
    rep.step("下載字幕(zh,自動)")
    rep.ok()
    assert buf.getvalue() == (
        "抓取影片資訊… ✓ 「片名」(9:59) → 模式 quick\n"
        "[1/3] 下載字幕(zh,自動)… ✓\n"
    )


def test_warn_breaks_the_open_line_and_indents():
    buf, rep = _rep()
    rep.set_total(4)
    rep.step("分段筆記 2 段")
    rep.warn("第 1 段失敗")
    rep.ok("1/2 段成功,1 段失敗")
    assert buf.getvalue() == (
        "[1/4] 分段筆記 2 段… \n"
        "      ⚠ 第 1 段失敗\n"
        "      ✓ 1/2 段成功,1 段失敗\n"
    )


def test_progress_counter_is_tty_only():
    buf, rep = _rep()                # isatty=False:不吐 \r 控制碼污染重導向的檔案
    rep.set_total(4)
    rep.step("分段筆記")
    rep.progress(1, 2)
    assert buf.getvalue() == "[1/4] 分段筆記… "

    tty_buf = io.StringIO()
    tty = Reporter(total_steps=4, stream=tty_buf, isatty=True)
    tty.step("分段筆記")
    tty.progress(1, 2)
    assert "1/2" in tty_buf.getvalue()
    assert "\r" in tty_buf.getvalue()


def test_quiet_writes_nothing():
    buf = io.StringIO()
    rep = Reporter(total_steps=4, stream=buf, enabled=False, isatty=False)
    rep.begin("抓取")
    rep.step("下載")
    rep.progress(1, 2)
    rep.warn("失敗")
    rep.ok("done")
    rep.close_line()
    assert buf.getvalue() == ""


def test_close_line_only_breaks_an_open_line():
    buf, rep = _rep()
    rep.set_total(4)
    rep.step("下載字幕")
    rep.close_line()                 # 例外中止:錯誤訊息不該黏在步驟行後面
    rep.close_line()                 # 冪等:已收尾就不再多印換行
    assert buf.getvalue() == "[1/4] 下載字幕… \n"
