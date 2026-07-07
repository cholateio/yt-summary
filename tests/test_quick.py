import pytest

from yt_summary.llm import LLMError, LLMResult
from yt_summary.quick import quick_summarize

TRANSCRIPT = {"video_id": "v", "title": "短片", "duration_sec": 300,
              "source": "auto_subs", "language": "zh-TW", "uploader": "",
              "upload_date": "", "webpage_url": "", "chapters": [],
              "sentences": [{"i": 0, "start": 0.0, "end": 3.0, "text": "哈囉"}]}


def test_quick_returns_article():
    def call(prompt, model, **kw):
        assert "哈囉" in prompt
        assert model == "opus"
        return LLMResult(text="# 短片文章", parsed=None, usage={}, cost_usd=0.0,
                         duration_sec=0.1, model=model)

    article, results = quick_summarize(TRANSCRIPT, "A", "opus", call=call)
    assert article == "# 短片文章"
    assert len(results) == 1


def test_quick_propagates_llm_error():
    def call(prompt, model, **kw):
        raise LLMError("boom")

    with pytest.raises(LLMError):
        quick_summarize(TRANSCRIPT, "A", "opus", call=call)
