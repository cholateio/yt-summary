# yt-summary v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YouTube 影片 → 重點文章 pipeline(長片 map-reduce / 短片單次呼叫),文章自動落地個人知識庫 vault/raw/。

**Architecture:** Python CLI。M1(yt-dlp 抓 metadata+字幕)→ M2(去重斷句)→ 依時長分流:quick(單次 claude -p)或 full(M3 切分 → M5 分段筆記 map → M6 整合 reduce)→ M8 落地 output/{video_id}/ → vault 匯出(原子寫入)。LLM 一律走 headless `claude -p`(訂閱內)。附 `remove` 子指令做事後移除。

**Tech Stack:** Python 3.12+、uv、yt-dlp(uv 依賴,以 CLI subprocess 呼叫)、pyyaml、pytest;LLM = Claude Code CLI(`claude -p --output-format json`)。

**權威 spec:** `docs/specs/2026-07-07-yt-summary-v1-design.md`(D1–D7)+ `docs/specs/yt-summary-spec.md`(v0.1,衝突時以前者為準)。

## Global Constraints

- Python ≥ 3.12;套件管理一律 uv;跑測試指令固定為 `uv run pytest -q`。
- 依賴僅 `yt-dlp`、`pyyaml`(dev 加 `pytest`);不得新增其他依賴。
- 執行環境需已登入 claude CLI(Claude Code 訂閱);單元測試一律 mock,不打真 LLM。
- LLM 呼叫唯一入口是 `llm.call_llm`;其他模組不得自行 subprocess claude。
- 模組函式收明確參數;只有 `cli.py` 讀 config.yaml。
- 輸出語言 zh-TW,專有名詞保留原文。
- vault 目錄 `/mnt/c/Users/micro/Documents/vault/`:程式只寫 `raw/`(原子寫入),**絕不寫 wiki/**;remove 對 wiki 只 grep 不改。
- v1 無 M7,故不產 `article_draft.md`,只產 `article_final.md`(對 spec §M8 的既定偏差)。
- 併發預設 2(claude -p 吃訂閱額度)。
- Commit 訊息:中文,`feat:`/`test:`/`docs:` 前綴。

## 資料契約(所有任務共用)

**transcript.json**(M2 產出):

```json
{
  "video_id": "abc123", "title": "...", "duration_sec": 2400,
  "source": "manual_subs | auto_subs", "language": "zh-TW",
  "uploader": "...", "upload_date": "20260701", "webpage_url": "https://...",
  "chapters": [{"title": "...", "start": 0.0, "end": 300.0}],
  "sentences": [{"i": 0, "start": 0.0, "end": 4.2, "text": "..."}]
}
```

**segment**(M3 產出,segments.json 為 `{"segments": [...]}`):

```json
{
  "segment_id": 0, "start": 0.0, "end": 612.5,
  "chapter_title": "章節名或 null", "context_prefix": "前段 overlap 文字或空字串",
  "sentences": [{"i": 0, "start": 0.0, "end": 4.2, "text": "..."}],
  "token_estimate": 3120
}
```

**segment_note**(M5 產出,spec §5.2 + status 欄):成功時為 spec 5.2 結構加 `"status": "ok"`;失敗時為 `{"segment_id": n, "status": "failed", "error": "..."}`。

**claude -p envelope**(2026-07-07 實測):

```json
{"type":"result","subtype":"success","is_error":false,"result":"<回覆文字>",
 "total_cost_usd":0.032,
 "usage":{"input_tokens":9,"cache_creation_input_tokens":15265,
          "cache_read_input_tokens":0,"output_tokens":333}}
```

---

### Task 1: 專案鷹架 + config 載入

**Files:**
- Create: `pyproject.toml`, `src/yt_summary/__init__.py`, `config.yaml`, `src/yt_summary/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.load_config(path: Path) -> Config`;`Config` 欄位:`language_out: str`、`concurrency: int`、`output_dir: Path`、`quick_threshold_sec: int`、`llm_models: dict[str, str]`(鍵 `m5`/`m6`/`quick`)、`vault_export: bool`、`vault_raw_dir: Path`、`types: dict[str, TypeConfig]`;`TypeConfig` 欄位:`segment_tokens: tuple[int, int]`、`overlap_sec: float`。

- [ ] **Step 1: 建骨架與 pyproject**

寫入 `pyproject.toml`:

```toml
[project]
name = "yt-summary"
version = "0.1.0"
description = "YouTube 影片轉重點文章 pipeline"
requires-python = ">=3.12"
dependencies = ["yt-dlp>=2025.1.1", "pyyaml>=6.0"]

[project.scripts]
yt-summary = "yt_summary.cli:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/yt_summary"]
```

建立 `src/yt_summary/__init__.py`(空檔)與 `tests/` 目錄。

- [ ] **Step 2: 寫入 config.yaml(repo 根目錄)**

```yaml
defaults:
  language_out: zh-TW
  concurrency: 2            # claude -p 訂閱額度考量
  output_dir: ./output

modes:
  quick_threshold_sec: 900  # < 15min 自動走 quick

llm:
  backend: claude-cli
  models: { m5: sonnet, m6: opus, quick: opus }

vault:
  export: true
  raw_dir: /mnt/c/Users/micro/Documents/vault/raw

types:
  A: { segment_tokens: [3000, 4000], overlap_sec: 45 }
  B: { segment_tokens: [3000, 4000], overlap_sec: 45 }
  C: { segment_tokens: [2000, 3000], overlap_sec: 30 }
```

- [ ] **Step 3: 寫失敗測試 `tests/test_config.py`**

```python
from pathlib import Path

from yt_summary.config import load_config

CONFIG_YAML = """\
defaults:
  language_out: zh-TW
  concurrency: 2
  output_dir: ./output
modes:
  quick_threshold_sec: 900
llm:
  backend: claude-cli
  models: { m5: sonnet, m6: opus, quick: opus }
vault:
  export: true
  raw_dir: /mnt/c/Users/micro/Documents/vault/raw
types:
  A: { segment_tokens: [3000, 4000], overlap_sec: 45 }
  B: { segment_tokens: [3000, 4000], overlap_sec: 45 }
  C: { segment_tokens: [2000, 3000], overlap_sec: 30 }
"""


def test_load_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(CONFIG_YAML, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.language_out == "zh-TW"
    assert cfg.concurrency == 2
    assert cfg.output_dir == Path("./output")
    assert cfg.quick_threshold_sec == 900
    assert cfg.llm_models == {"m5": "sonnet", "m6": "opus", "quick": "opus"}
    assert cfg.vault_export is True
    assert cfg.vault_raw_dir == Path("/mnt/c/Users/micro/Documents/vault/raw")
    assert cfg.types["A"].segment_tokens == (3000, 4000)
    assert cfg.types["C"].overlap_sec == 30.0
```

- [ ] **Step 4: 跑測試確認失敗**

Run: `uv run pytest -q`(首次會自動建 venv 並安裝依賴)
Expected: FAIL,`ModuleNotFoundError: No module named 'yt_summary.config'`

- [ ] **Step 5: 實作 `src/yt_summary/config.py`**

```python
"""config.yaml 載入。只有 cli.py 使用;其他模組收明確參數。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TypeConfig:
    segment_tokens: tuple[int, int]
    overlap_sec: float


@dataclass(frozen=True)
class Config:
    language_out: str
    concurrency: int
    output_dir: Path
    quick_threshold_sec: int
    llm_models: dict[str, str]
    vault_export: bool
    vault_raw_dir: Path
    types: dict[str, TypeConfig]


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    d = raw.get("defaults", {})
    vault = raw.get("vault", {})
    types = {
        key: TypeConfig(
            segment_tokens=tuple(val["segment_tokens"]),
            overlap_sec=float(val["overlap_sec"]),
        )
        for key, val in raw.get("types", {}).items()
    }
    return Config(
        language_out=d.get("language_out", "zh-TW"),
        concurrency=int(d.get("concurrency", 2)),
        output_dir=Path(d.get("output_dir", "./output")),
        quick_threshold_sec=int(raw.get("modes", {}).get("quick_threshold_sec", 900)),
        llm_models=dict(
            raw.get("llm", {}).get("models", {"m5": "sonnet", "m6": "opus", "quick": "opus"})
        ),
        vault_export=bool(vault.get("export", True)),
        vault_raw_dir=Path(vault.get("raw_dir", "")),
        types=types,
    )
```

- [ ] **Step 6: 跑測試確認通過**

Run: `uv run pytest -q`
Expected: `1 passed`

- [ ] **Step 7: 加 .gitignore 並 commit**

`.gitignore` 追加(檔案已存在則 append):

```
.venv/
output/
__pycache__/
*.egg-info/
```

```bash
git add pyproject.toml uv.lock config.yaml src/ tests/ .gitignore
git commit -m "feat: 專案鷹架(uv/pyproject)+ config 載入"
```

---

### Task 2: tokens.py(token 估算)

**Files:**
- Create: `src/yt_summary/tokens.py`
- Test: `tests/test_tokens.py`

**Interfaces:**
- Produces: `tokens.estimate_tokens(text: str) -> int`(啟發式:CJK 字元 ×1.0 + 非 CJK 詞 ×1.3,四捨五入)。

- [ ] **Step 1: 寫失敗測試 `tests/test_tokens.py`**

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_tokens.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/tokens.py`**

```python
"""啟發式 token 估算(spec 允許 ±10% 誤差,不引入 tokenizer 依賴)。"""
import re

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
_WORD = re.compile(r"[A-Za-z0-9_]+")


def estimate_tokens(text: str) -> int:
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(text))
    return round(cjk * 1.0 + words * 1.3)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_tokens.py`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/tokens.py tests/test_tokens.py
git commit -m "feat: token 啟發式估算"
```

---

### Task 3: llm.py(claude -p wrapper)

**Files:**
- Create: `src/yt_summary/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces:
  - `llm.LLMError(Exception)`
  - `llm.LLMResult`(dataclass:`text: str`、`parsed: dict | list | None`、`usage: dict`、`cost_usd: float`、`duration_sec: float`、`model: str`)
  - `llm.call_llm(prompt: str, model: str, expect_json: bool = False, *, timeout_sec=1800, retries=1, retry_wait_sec=30, run=subprocess.run, sleep=time.sleep) -> LLMResult`
- 行為契約:非零退出/envelope 壞 → 等 `retry_wait_sec` 重試 `retries` 次,再失敗 raise `LLMError`;`expect_json` 內容解析失敗 → 一次修復呼叫(壞輸出丟回同模型),再失敗 raise `LLMError`;修復呼叫的 usage/cost 併入結果。

- [ ] **Step 1: 寫失敗測試 `tests/test_llm.py`**

```python
import json
import subprocess

import pytest

from yt_summary.llm import LLMError, call_llm


def _envelope(result_text, cost=0.01, is_error=False):
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": is_error,
        "result": result_text, "total_cost_usd": cost,
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
                  "cache_read_input_tokens": 0, "output_tokens": 7},
    })


def _fake_run(responses):
    """responses: list of (returncode, stdout, stderr);依呼叫次序回傳。"""
    calls = []

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        calls.append({"cmd": cmd, "input": input})
        rc, out, err = responses[len(calls) - 1]
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)

    run.calls = calls
    return run


def test_plain_text_success():
    run = _fake_run([(0, _envelope("答案文字"), "")])
    r = call_llm("問題", model="sonnet", run=run)
    assert r.text == "答案文字"
    assert r.parsed is None
    assert r.cost_usd == 0.01
    assert r.usage["output_tokens"] == 7
    assert r.model == "sonnet"
    # prompt 走 stdin,cmd 含 --model 與 --tools ""
    assert run.calls[0]["input"] == "問題"
    assert "--model" in run.calls[0]["cmd"] and "sonnet" in run.calls[0]["cmd"]
    assert "--tools" in run.calls[0]["cmd"]


def test_expect_json_with_fence():
    run = _fake_run([(0, _envelope('```json\n{"a": 1}\n```'), "")])
    r = call_llm("p", model="sonnet", expect_json=True, run=run)
    assert r.parsed == {"a": 1}


def test_expect_json_repair_retry():
    run = _fake_run([
        (0, _envelope('{"a": 1,,}'), ""),      # 壞 JSON
        (0, _envelope('{"a": 1}', cost=0.02), ""),  # 修復成功
    ])
    r = call_llm("p", model="sonnet", expect_json=True, run=run)
    assert r.parsed == {"a": 1}
    assert len(run.calls) == 2
    assert "修" in run.calls[1]["input"] or "JSON" in run.calls[1]["input"]
    assert r.cost_usd == pytest.approx(0.03)  # 兩次呼叫成本合併
    assert r.usage["input_tokens"] == 20      # usage 合併


def test_expect_json_repair_fails():
    run = _fake_run([(0, _envelope("不是 json"), ""), (0, _envelope("還是不是"), "")])
    with pytest.raises(LLMError):
        call_llm("p", model="sonnet", expect_json=True, run=run)


def test_nonzero_exit_retries_then_succeeds():
    slept = []
    run = _fake_run([(1, "", "boom"), (0, _envelope("ok"), "")])
    r = call_llm("p", model="opus", run=run, sleep=slept.append, retry_wait_sec=30)
    assert r.text == "ok"
    assert slept == [30]


def test_nonzero_exit_exhausts_retries():
    run = _fake_run([(1, "", "boom"), (1, "", "boom")])
    with pytest.raises(LLMError):
        call_llm("p", model="opus", run=run, sleep=lambda s: None)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_llm.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/llm.py`**

```python
"""claude -p wrapper:整個專案唯一的 LLM 呼叫入口(design D5)。"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass

_CLI_BASE = ["claude", "-p", "--output-format", "json", "--tools", ""]

_REPAIR_PROMPT = (
    "下面這段輸出應該是合法 JSON,但解析失敗。"
    "請把它修成合法 JSON,只輸出修好的 JSON,不要任何說明文字:\n\n"
)


class LLMError(Exception):
    """claude -p 呼叫失敗(重試後仍失敗、或 JSON 修不回來)。"""


@dataclass
class LLMResult:
    text: str
    parsed: dict | list | None
    usage: dict
    cost_usd: float
    duration_sec: float
    model: str


def _extract_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[A-Za-z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[}\]]", t, re.S)
        if m is None:
            raise
        return json.loads(m.group(0))


def _merge_usage(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, (int, float)) and isinstance(out.get(k, 0), (int, float)):
            out[k] = out.get(k, 0) + v
    return out


def _invoke(prompt: str, model: str, timeout_sec: int, run):
    proc = run(
        _CLI_BASE + ["--model", model],
        input=prompt, capture_output=True, text=True, timeout=timeout_sec,
    )
    if proc.returncode != 0:
        raise LLMError(f"claude -p exit={proc.returncode}:{(proc.stderr or '')[-500:]}")
    data = json.loads(proc.stdout)
    if data.get("is_error"):
        raise LLMError(f"claude -p 回報錯誤:{str(data.get('result'))[:500]}")
    return data


def call_llm(
    prompt: str,
    model: str,
    expect_json: bool = False,
    *,
    timeout_sec: int = 1800,
    retries: int = 1,
    retry_wait_sec: int = 30,
    run=subprocess.run,
    sleep=time.sleep,
) -> LLMResult:
    start = time.monotonic()
    attempt = 0
    while True:
        try:
            data = _invoke(prompt, model, timeout_sec, run)
            break
        except (LLMError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            attempt += 1
            if attempt > retries:
                raise LLMError(f"claude -p 重試後仍失敗:{e}") from e
            sleep(retry_wait_sec)

    text = data.get("result") or ""
    usage = data.get("usage") or {}
    cost = float(data.get("total_cost_usd") or 0.0)
    parsed = None

    if expect_json:
        try:
            parsed = _extract_json(text)
        except json.JSONDecodeError:
            try:
                repair = _invoke(_REPAIR_PROMPT + text, model, timeout_sec, run)
            except (LLMError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
                raise LLMError(f"JSON 修復呼叫失敗:{e}") from e
            usage = _merge_usage(usage, repair.get("usage") or {})
            cost += float(repair.get("total_cost_usd") or 0.0)
            text = repair.get("result") or ""
            try:
                parsed = _extract_json(text)
            except json.JSONDecodeError as e:
                raise LLMError("JSON 修復後仍解析失敗") from e

    return LLMResult(
        text=text, parsed=parsed, usage=usage, cost_usd=cost,
        duration_sec=time.monotonic() - start, model=model,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_llm.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/llm.py tests/test_llm.py
git commit -m "feat: claude -p LLM wrapper(JSON 修復重試、usage 記錄)"
```

---

### Task 4: m1_fetch.py(metadata + 字幕下載)

**Files:**
- Create: `src/yt_summary/m1_fetch.py`
- Test: `tests/test_m1_fetch.py`

**Interfaces:**
- Produces:
  - `m1_fetch.FetchError(Exception)`
  - `m1_fetch.DEFAULT_LANG_PRIORITY = ["zh-TW", "zh-Hant", "zh", "en"]`
  - `m1_fetch.fetch_meta(url: str, run=subprocess.run) -> dict`(yt-dlp `--dump-json` 的原始 dict)
  - `m1_fetch.pick_subtitle_lang(meta: dict, priority=DEFAULT_LANG_PRIORITY) -> tuple[str, str] | None`(回傳 `(lang, "manual_subs"|"auto_subs")`,人工優先)
  - `m1_fetch.download_subtitle(url: str, lang: str, source: str, workdir: Path, run=subprocess.run) -> Path`(json3 檔路徑)

- [ ] **Step 1: 寫失敗測試 `tests/test_m1_fetch.py`**

```python
import json
import subprocess

import pytest

from yt_summary.m1_fetch import (
    FetchError, download_subtitle, fetch_meta, pick_subtitle_lang,
)


def _run_factory(responses):
    calls = []

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        calls.append(cmd)
        rc, out, err = responses[len(calls) - 1]
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)

    run.calls = calls
    return run


META = {"id": "abcdefghijk", "title": "測試影片", "duration": 600,
        "subtitles": {}, "automatic_captions": {"zh-TW": [{"ext": "json3"}]}}


def test_fetch_meta_ok():
    run = _run_factory([(0, json.dumps(META), "")])
    meta = fetch_meta("https://youtu.be/abcdefghijk", run=run)
    assert meta["id"] == "abcdefghijk"
    assert "--no-playlist" in run.calls[0]


def test_fetch_meta_failure_raises():
    run = _run_factory([(1, "", "ERROR: Video unavailable")])
    with pytest.raises(FetchError, match="Video unavailable"):
        fetch_meta("https://youtu.be/x", run=run)


def test_pick_manual_over_auto():
    meta = {"subtitles": {"en": [{}]}, "automatic_captions": {"zh-TW": [{}]}}
    assert pick_subtitle_lang(meta) == ("en", "manual_subs")


def test_pick_priority_order_within_auto():
    meta = {"subtitles": {}, "automatic_captions": {"en": [{}], "zh-TW": [{}]}}
    assert pick_subtitle_lang(meta) == ("zh-TW", "auto_subs")


def test_pick_none_when_no_subs():
    assert pick_subtitle_lang({"subtitles": {}, "automatic_captions": {}}) is None


def test_download_subtitle_finds_file(tmp_path):
    sub = tmp_path / "abcdefghijk.zh-TW.json3"

    def run(cmd, input=None, capture_output=None, text=None, timeout=None):
        sub.write_text("{}", encoding="utf-8")
        assert "--write-auto-subs" in cmd  # auto_subs 用 auto 旗標
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    path = download_subtitle("u", "zh-TW", "auto_subs", tmp_path, run=run)
    assert path == sub


def test_download_subtitle_missing_file_raises(tmp_path):
    run = _run_factory([(0, "", "")])
    with pytest.raises(FetchError, match="未找到"):
        download_subtitle("u", "zh-TW", "manual_subs", tmp_path, run=run)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_m1_fetch.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/m1_fetch.py`**

```python
"""M1 擷取:yt-dlp metadata + 字幕下載(v1 只走字幕路徑,無 Whisper)。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

DEFAULT_LANG_PRIORITY = ["zh-TW", "zh-Hant", "zh", "en"]


class FetchError(Exception):
    """影片不可用 / 無字幕 / yt-dlp 失敗。"""


def fetch_meta(url: str, run=subprocess.run) -> dict:
    proc = run(
        ["yt-dlp", "--dump-json", "--no-download", "--no-playlist", url],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise FetchError(f"yt-dlp metadata 失敗:{(proc.stderr or '')[-500:]}")
    first_line = proc.stdout.strip().splitlines()[0]
    return json.loads(first_line)


def pick_subtitle_lang(meta: dict, priority=DEFAULT_LANG_PRIORITY):
    manual = meta.get("subtitles") or {}
    auto = meta.get("automatic_captions") or {}
    for lang in priority:
        if manual.get(lang):
            return lang, "manual_subs"
    for lang in priority:
        if auto.get(lang):
            return lang, "auto_subs"
    return None


def download_subtitle(url: str, lang: str, source: str, workdir: Path,
                      run=subprocess.run) -> Path:
    flag = "--write-subs" if source == "manual_subs" else "--write-auto-subs"
    proc = run(
        ["yt-dlp", "--skip-download", "--no-playlist", flag,
         "--sub-langs", lang, "--sub-format", "json3",
         "-o", str(Path(workdir) / "%(id)s.%(ext)s"), url],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise FetchError(f"yt-dlp 字幕下載失敗:{(proc.stderr or '')[-500:]}")
    candidates = sorted(Path(workdir).glob("*.json3"))
    if not candidates:
        raise FetchError("字幕檔下載後未找到(.json3)")
    return candidates[0]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_m1_fetch.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/m1_fetch.py tests/test_m1_fetch.py
git commit -m "feat: M1 擷取(yt-dlp metadata、字幕語言優先序、json3 下載)"
```

---

### Task 5: m2_clean.py(去重、斷句、transcript)

**Files:**
- Create: `src/yt_summary/m2_clean.py`
- Test: `tests/test_m2_clean.py`

**Interfaces:**
- Consumes: 無(純函式)。
- Produces:
  - `m2_clean.parse_json3(path: Path) -> list[dict]`(cue = `{"start": float, "end": float, "text": str}`)
  - `m2_clean.dedup_cues(cues: list[dict]) -> list[dict]`
  - `m2_clean.split_sentences(cues, gap_sec=0.8, max_chars=120) -> list[dict]`(sentence = `{"i", "start", "end", "text"}`)
  - `m2_clean.build_transcript(meta: dict, sentences: list[dict], source: str, language: str) -> dict`(資料契約 transcript.json)

- [ ] **Step 1: 寫失敗測試 `tests/test_m2_clean.py`**

```python
import json

from yt_summary.m2_clean import (
    build_transcript, dedup_cues, parse_json3, split_sentences,
)


def _cue(start, end, text):
    return {"start": start, "end": end, "text": text}


def test_parse_json3(tmp_path):
    data = {"events": [
        {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "大家好"}]},
        {"tStartMs": 2000, "dDurationMs": 1500, "segs": [{"utf8": "今天"}, {"utf8": "聊聊"}]},
        {"tStartMs": 4000, "dDurationMs": 1000},  # 無 segs → 略過
    ]}
    p = tmp_path / "s.json3"
    p.write_text(json.dumps(data), encoding="utf-8")
    cues = parse_json3(p)
    assert cues == [_cue(0.0, 2.0, "大家好"), _cue(2.0, 3.5, "今天聊聊")]


def test_dedup_rolling_captions():
    cues = [
        _cue(0, 2, "今天我們要聊"),
        _cue(2, 4, "今天我們要聊 AI 工具"),   # 前綴重複
        _cue(4, 6, "AI 工具"),               # 完全被前句尾包含 → 丟棄
        _cue(6, 8, "的使用方式"),
    ]
    out = dedup_cues(cues)
    assert [c["text"] for c in out] == ["今天我們要聊", "AI 工具", "的使用方式"]


def test_split_on_gap():
    cues = [_cue(0, 1, "第一句沒有標點"), _cue(3, 4, "第二句")]  # gap 2s > 0.8
    sents = split_sentences(cues)
    assert len(sents) == 2
    assert sents[0]["text"] == "第一句沒有標點"
    assert sents[0]["start"] == 0 and sents[0]["end"] == 1
    assert sents[1]["i"] == 1


def test_split_on_punctuation():
    cues = [_cue(0, 1, "先講結論。"), _cue(1.2, 2, "再講原因")]
    sents = split_sentences(cues)
    assert [s["text"] for s in sents] == ["先講結論。", "再講原因"]


def test_ascii_join_inserts_space():
    cues = [_cue(0, 1, "we use"), _cue(1.1, 2, "pytest here")]
    sents = split_sentences(cues)
    assert sents[0]["text"] == "we use pytest here"


def test_build_transcript():
    meta = {"id": "abc", "title": "T", "duration": 100, "uploader": "U",
            "upload_date": "20260701", "webpage_url": "https://youtu.be/abc",
            "chapters": [{"title": "開場", "start_time": 0, "end_time": 50}]}
    sents = [{"i": 0, "start": 0.0, "end": 1.0, "text": "hi"}]
    t = build_transcript(meta, sents, "auto_subs", "zh-TW")
    assert t["video_id"] == "abc"
    assert t["duration_sec"] == 100
    assert t["source"] == "auto_subs"
    assert t["chapters"] == [{"title": "開場", "start": 0.0, "end": 50.0}]
    assert t["sentences"] == sents
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_m2_clean.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/m2_clean.py`**

```python
"""M2 前處理:json3 解析、滾動字幕去重、規則法斷句、transcript 組裝。"""
from __future__ import annotations

import json
from pathlib import Path

_SENT_END = "。!?!?;;"


def parse_json3(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cues = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000.0
        end = start + ev.get("dDurationMs", 0) / 1000.0
        cues.append({"start": start, "end": end, "text": text})
    return cues


def _longest_overlap(a: str, b: str) -> int:
    for k in range(min(len(a), len(b)), 0, -1):
        if a[-k:] == b[:k]:
            return k
    return 0


def dedup_cues(cues: list[dict]) -> list[dict]:
    out: list[dict] = []
    for cue in cues:
        text = cue["text"]
        if out:
            k = _longest_overlap(out[-1]["text"], text)
            text = text[k:].strip()
            if not text:
                continue
        out.append({**cue, "text": text})
    return out


def _join(parts: list[str]) -> str:
    buf = ""
    for p in parts:
        if buf and buf[-1].isascii() and buf[-1].isalnum() \
                and p and p[0].isascii() and p[0].isalnum():
            buf += " "
        buf += p
    return buf.strip()


def split_sentences(cues: list[dict], gap_sec: float = 0.8,
                    max_chars: int = 120) -> list[dict]:
    sentences: list[dict] = []
    parts: list[str] = []
    buf_start = buf_end = 0.0

    def flush():
        nonlocal parts
        text = _join(parts)
        if text:
            sentences.append({"i": len(sentences), "start": buf_start,
                              "end": buf_end, "text": text})
        parts = []

    for cue in cues:
        if parts and cue["start"] - buf_end > gap_sec:
            flush()
        if not parts:
            buf_start = cue["start"]
        parts.append(cue["text"])
        buf_end = cue["end"]
        joined = _join(parts)
        if joined and (joined[-1] in _SENT_END or len(joined) >= max_chars):
            flush()
    flush()
    return sentences


def build_transcript(meta: dict, sentences: list[dict], source: str,
                     language: str) -> dict:
    chapters = [
        {"title": c.get("title", ""), "start": float(c.get("start_time") or 0),
         "end": float(c.get("end_time") or 0)}
        for c in (meta.get("chapters") or [])
    ]
    return {
        "video_id": meta["id"],
        "title": meta.get("title", ""),
        "duration_sec": int(meta.get("duration") or 0),
        "source": source,
        "language": language,
        "uploader": meta.get("uploader", ""),
        "upload_date": meta.get("upload_date", ""),
        "webpage_url": meta.get("webpage_url", ""),
        "chapters": chapters,
        "sentences": sentences,
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_m2_clean.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/m2_clean.py tests/test_m2_clean.py
git commit -m "feat: M2 前處理(json3 解析、滾動去重、規則斷句)"
```

---

### Task 6: m3_segment.py(切分)

**Files:**
- Create: `src/yt_summary/m3_segment.py`
- Test: `tests/test_m3_segment.py`

**Interfaces:**
- Consumes: `tokens.estimate_tokens`(可注入)。
- Produces:
  - `m3_segment.chapters_meaningful(chapters: list[dict]) -> bool`
  - `m3_segment.segment(transcript: dict, segment_tokens: tuple[int, int], overlap_sec: float, min_chapter_tokens: int = 800, estimate=estimate_tokens) -> list[dict]`(資料契約 segment;首段 `context_prefix` 為空字串)

- [ ] **Step 1: 寫失敗測試 `tests/test_m3_segment.py`**

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_m3_segment.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/m3_segment.py`**

```python
"""M3 切分:章節優先,否則 token 窗;overlap 以 context_prefix 附帶。"""
from __future__ import annotations

import re

from .tokens import estimate_tokens

GENERIC_CHAPTER = re.compile(
    r"^\s*(part|chapter|section|ep|episode|第?\s*[0-9一二三四五六七八九十]+\s*(部分|章|節|集)?)\s*[0-9]*\s*$",
    re.IGNORECASE,
)


def chapters_meaningful(chapters: list[dict]) -> bool:
    if not chapters:
        return False
    generic = sum(1 for c in chapters if GENERIC_CHAPTER.match(c.get("title") or ""))
    return generic <= len(chapters) / 2


def _window(sentences: list[dict], hi: int, estimate) -> list[list[dict]]:
    """token 窗切分,邊界對齊句尾。"""
    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_tokens = 0
    for s in sentences:
        t = estimate(s["text"])
        if cur and cur_tokens + t > hi:
            groups.append(cur)
            cur, cur_tokens = [], 0
        cur.append(s)
        cur_tokens += t
    if cur:
        groups.append(cur)
    return groups


def _by_chapters(chapters: list[dict], sentences: list[dict]) -> list[tuple[str, list[dict]]]:
    buckets: list[tuple[str, list[dict]]] = [(c["title"], []) for c in chapters]
    starts = [c["start"] for c in chapters]
    for s in sentences:
        idx = 0
        for j, st in enumerate(starts):
            if s["start"] >= st:
                idx = j
        buckets[idx][1].append(s)
    return [(t, g) for t, g in buckets if g]


def segment(transcript: dict, segment_tokens: tuple[int, int], overlap_sec: float,
            min_chapter_tokens: int = 800, estimate=estimate_tokens) -> list[dict]:
    lo, hi = segment_tokens
    sents = transcript["sentences"]
    if not sents:
        return []

    if chapters_meaningful(transcript.get("chapters") or []):
        buckets = _by_chapters(transcript["chapters"], sents)
        merged: list[tuple[str, list[dict]]] = []
        for title, group in buckets:
            tok = sum(estimate(s["text"]) for s in group)
            if tok < min_chapter_tokens and merged:
                merged[-1] = (merged[-1][0], merged[-1][1] + group)
            elif tok < min_chapter_tokens and not merged:
                merged.append((title, list(group)))  # 首章太小:先收,待下章合併
            else:
                if merged and sum(estimate(s["text"]) for s in merged[-1][1]) < min_chapter_tokens:
                    merged[-1] = (title, merged[-1][1] + list(group))  # 前章太小併入本章
                else:
                    merged.append((title, list(group)))
        groups = [(title, g) for title, group in merged
                  for g in _window(group, hi, estimate)]
    else:
        groups = [(None, g) for g in _window(sents, hi, estimate)]

    segments = []
    for idx, (title, group) in enumerate(groups):
        start, end = group[0]["start"], group[-1]["end"]
        prefix = ""
        if idx > 0:
            prefix_sents = [s for s in sents if start - overlap_sec <= s["start"] < start]
            prefix = " ".join(s["text"] for s in prefix_sents)
        segments.append({
            "segment_id": idx,
            "start": start,
            "end": end,
            "chapter_title": title,
            "context_prefix": prefix,
            "sentences": group,
            "token_estimate": sum(estimate(s["text"]) for s in group),
        })
    return segments
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_m3_segment.py`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/m3_segment.py tests/test_m3_segment.py
git commit -m "feat: M3 切分(章節優先、token 窗、overlap prefix、小章節合併)"
```

---

### Task 7: prompts.py(prompt 模板)

**Files:**
- Create: `src/yt_summary/prompts.py`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: segment / transcript / note 資料契約。
- Produces:
  - `prompts.ts(sec: float) -> str`(`m:ss` 或 `h:mm:ss`)
  - `prompts.TYPE_RULES: dict[str, str]`(鍵 `A`/`B`/`C`)
  - `prompts.m5_prompt(segment: dict, transcript: dict, type_code: str) -> str`
  - `prompts.render_note_block(note: dict) -> str`(note JSON → markdown 區塊)
  - `prompts.m6_prompt(blocks: list[str], transcript: dict, type_code: str, failed_segment_ids: list[int]) -> str`
  - `prompts.m6_mid_prompt(blocks: list[str], transcript: dict, type_code: str) -> str`
  - `prompts.quick_prompt(transcript: dict, type_code: str) -> str`

- [ ] **Step 1: 寫失敗測試 `tests/test_prompts.py`**

```python
from yt_summary import prompts

TRANSCRIPT = {
    "video_id": "v1", "title": "量化交易入門", "duration_sec": 700,
    "source": "auto_subs", "language": "zh-TW", "uploader": "頻道",
    "upload_date": "20260701", "webpage_url": "https://youtu.be/v1",
    "chapters": [],
    "sentences": [{"i": 0, "start": 0.0, "end": 4.0, "text": "年化 14.2% 的策略"}],
}

SEGMENT = {"segment_id": 2, "start": 612.0, "end": 1180.5,
           "chapter_title": "回測", "context_prefix": "前段講了均線。",
           "sentences": TRANSCRIPT["sentences"], "token_estimate": 10}

NOTE = {"segment_id": 2, "status": "ok", "time_range": [612.0, 1180.5],
        "topic": "回測陷阱",
        "points": [{"claim": "過度擬合是主因", "timestamp": 645.2,
                    "evidence_quote": "原句", "importance": 3, "confidence": "low"}],
        "entities": ["backtrader"],
        "facts_numbers": [{"value": "年化 14.2%", "context": "策略績效", "timestamp": 700.1}],
        "code_blocks": [{"lang": "python", "code": "x = 1", "timestamp": 820.0, "note": ""}],
        "speaker_emphasis": ["這個很重要"]}


def test_ts_format():
    assert prompts.ts(65) == "1:05"
    assert prompts.ts(3661) == "1:01:01"


def test_m5_prompt_contains_essentials():
    p = prompts.m5_prompt(SEGMENT, TRANSCRIPT, "B")
    assert "[10:12]" in p                      # 時間戳行
    assert "前段講了均線。" in p                 # context_prefix
    assert "僅供理解" in p                      # prefix 指示
    assert "原樣抄錄" in p                      # Type B 規則
    assert '"segment_id": 2' in p              # schema 綁定段落 id
    assert "ASR" in p                          # auto_subs → 錯字推斷註記
    assert "confidence" in p


def test_m5_prompt_type_a_no_number_rule():
    p = prompts.m5_prompt(SEGMENT, TRANSCRIPT, "A")
    assert "原樣抄錄" not in p
    assert "推理鏈" in p


def test_render_note_block():
    b = prompts.render_note_block(NOTE)
    assert "回測陷阱" in b
    assert "過度擬合是主因" in b
    assert "10:45" in b            # 645.2s → 10:45
    assert "年化 14.2%" in b
    assert "```python" in b
    assert "confidence: low" in b
    assert "這個很重要" in b


def test_m6_prompt():
    p = prompts.m6_prompt(["區塊一", "區塊二"], TRANSCRIPT, "B", failed_segment_ids=[3])
    assert "TL;DR" in p
    assert "數字彙整表" in p       # Type B 附錄
    assert "區塊一" in p and "區塊二" in p
    assert "第 3 段" in p          # 缺段警告
    assert "[mm:ss]" in p or "時間戳" in p


def test_quick_prompt():
    p = prompts.quick_prompt(TRANSCRIPT, "C")
    assert "年化 14.2% 的策略" in p     # 全逐字稿
    assert "[0:00]" in p
    assert "程式碼" in p               # Type C 規則
    assert "TL;DR" in p
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_prompts.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/prompts.py`**

```python
"""所有 LLM prompt 模板;type 特化規則集中此處(design D3)。"""
from __future__ import annotations

TYPE_RULES = {
    "A": "- 保留論點的推理鏈:不只記結論,也要記講者「為什麼」這樣主張。",
    "B": ("- 所有數字、百分比、日期、股票/商品代號、指標名稱必須原樣抄錄,"
          "禁止改寫為「大約」「不錯」等模糊描述。"),
    "C": ("- 程式碼、檔案名稱、函式名、指令列參數原樣保留;"
          "講者口述的實作步驟完整記錄,勿簡化。"),
}

_APPENDIX_RULES = {
    "A": "附錄:提及的工具/資源清單。",
    "B": "附錄「必須」包含:數字彙整表(數值|說明|時間戳)。",
    "C": "附錄「必須」包含:完整程式碼區塊(每塊標對應時間戳)。",
}

_ASR_NOTE = ("本字幕由 ASR 自動產生,可能有錯字:遇疑似錯字依上下文合理推斷,"
             "並將該論點標 confidence: \"low\"。")

_NOTE_SCHEMA = """{
  "segment_id": %d,
  "time_range": [%s, %s],
  "topic": "本段主題一句話",
  "points": [
    {"claim": "論點完整敘述", "timestamp": 0.0,
     "evidence_quote": "逐字稿原句(可截短)", "importance": 3, "confidence": "high"}
  ],
  "entities": ["工具名", "專有名詞"],
  "facts_numbers": [{"value": "數值原文", "context": "一句說明", "timestamp": 0.0}],
  "code_blocks": [{"lang": "語言", "code": "程式碼", "timestamp": 0.0, "note": "口述與畫面差異(若有)"}],
  "speaker_emphasis": ["講者明示重要的內容"]
}"""


def ts(sec: float) -> str:
    s = int(sec)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_sentences(sentences: list[dict]) -> str:
    return "\n".join(f"[{ts(s['start'])}] {s['text']}" for s in sentences)


def _meta_block(transcript: dict, extra: str = "") -> str:
    lines = [
        f"- 標題:{transcript['title']}",
        f"- 頻道:{transcript.get('uploader', '')}",
        f"- 時長:{ts(transcript['duration_sec'])}",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def m5_prompt(segment: dict, transcript: dict, type_code: str) -> str:
    asr = f"5. {_ASR_NOTE}\n" if transcript.get("source") == "auto_subs" else ""
    prefix = segment.get("context_prefix") or "(無)"
    schema = _NOTE_SCHEMA % (segment["segment_id"], segment["start"], segment["end"])
    return f"""你是逐字稿分析員,任務是「不遺漏地記錄」以下影片段落的所有內容。

## 影片資訊
{_meta_block(transcript, f"- 章節:{segment.get('chapter_title') or '(無)'}")}
- 本段時間範圍:{ts(segment['start'])}–{ts(segment['end'])}

## 前段脈絡(僅供理解,不需記錄)
{prefix}

## 本段逐字稿(每行開頭為時間戳)
{_format_sentences(segment['sentences'])}

## 任務要求
1. 寧可冗長,不可精簡——壓縮是後續階段的事。
2. 不得省略「看似次要」的論點;不確定的內容標 confidence: "low" 而不是丟棄。
3. 每個論點附時間戳(秒數,浮點數)與一句逐字稿原文依據(evidence_quote)。
4. 講者明示的重點(「這個很重要」「記下來」)收進 speaker_emphasis。
{asr}{TYPE_RULES[type_code]}

## 輸出格式
只輸出一個合法 JSON 物件,不要任何其他文字。schema(含本段固定值):
{schema}
"""


def render_note_block(note: dict) -> str:
    lines = [f"### 段落 {note.get('segment_id')}:{note.get('topic', '')}"]
    tr = note.get("time_range")
    if tr:
        lines.append(f"時間範圍:{ts(tr[0])}–{ts(tr[1])}")
    for p in note.get("points", []):
        conf = "(confidence: low)" if p.get("confidence") == "low" else ""
        lines.append(f"- [{ts(p.get('timestamp', 0))}] {p.get('claim', '')}{conf}")
        if p.get("evidence_quote"):
            lines.append(f"  依據:「{p['evidence_quote']}」")
    if note.get("entities"):
        lines.append("工具/專有名詞:" + "、".join(note["entities"]))
    for f in note.get("facts_numbers", []):
        lines.append(f"- 數字:[{ts(f.get('timestamp', 0))}] {f.get('value', '')} — {f.get('context', '')}")
    for cb in note.get("code_blocks", []):
        lines.append(f"```{cb.get('lang', '')}\n{cb.get('code', '')}\n```")
        if cb.get("note"):
            lines.append(f"(註:{cb['note']})")
    if note.get("speaker_emphasis"):
        lines.append("講者強調:" + ";".join(note["speaker_emphasis"]))
    return "\n".join(lines)


def _failed_note(failed_segment_ids: list[int]) -> str:
    if not failed_segment_ids:
        return ""
    ids = "、".join(f"第 {i} 段" for i in failed_segment_ids)
    return f"\n注意:{ids}的筆記產生失敗,請在文章開頭以引言區塊註明該段內容缺漏。\n"


def m6_prompt(blocks: list[str], transcript: dict, type_code: str,
              failed_segment_ids: list[int]) -> str:
    joined = "\n\n---\n\n".join(blocks)
    return f"""你是技術寫作者。以下是一支影片各段落的詳細筆記,請整合成一篇結構完整的 zh-TW 文章。

## 影片資訊
{_meta_block(transcript)}

## 整合規則
1. 資訊留存為第一優先,可讀性第二;不得為了流暢而丟論點。
2. 相鄰段落因重疊造成的重複論點需合併,但不同角度的重述要保留。
3. 每個主要論點後附時間戳,格式 [mm:ss](超過一小時用 [h:mm:ss]),讓讀者可跳回原片。
4. 文章結構:開頭 TL;DR(5–8 條)→ 依主題重組的正文(不必然照影片順序)→ 附錄。
5. {_APPENDIX_RULES[type_code]}
6. 專有名詞保留原文;{TYPE_RULES[type_code]}
{_failed_note(failed_segment_ids)}
## 分段筆記
{joined}

只輸出文章 markdown,不要任何其他說明。
"""


def m6_mid_prompt(blocks: list[str], transcript: dict, type_code: str) -> str:
    joined = "\n\n---\n\n".join(blocks)
    return f"""以下是影片「{transcript['title']}」相鄰數段的詳細筆記。
請合併成一份「合併筆記」:去除重疊重複的論點、保留所有獨立論點與其時間戳。
{TYPE_RULES[type_code]}
輸出 markdown 條列(維持與輸入相同的格式),不要文章化,不得省略任何獨立論點。

{joined}
"""


def quick_prompt(transcript: dict, type_code: str) -> str:
    asr = f"\n4. {_ASR_NOTE}" if transcript.get("source") == "auto_subs" else ""
    return f"""你是逐字稿分析員兼技術寫作者。以下是一支短影片的完整逐字稿,請直接產出一篇 zh-TW「重點文章」。

## 影片資訊
{_meta_block(transcript)}

## 逐字稿(每行開頭為時間戳)
{_format_sentences(transcript['sentences'])}

## 要求
1. 資訊留存為第一優先:不得省略「看似次要」的論點;數字、專有名詞、程式碼保留原文。
2. 文章結構:開頭 TL;DR(3–6 條)→ 依主題重組的正文,每個主要論點附 [mm:ss] 時間戳 → {_APPENDIX_RULES[type_code]}
3. {TYPE_RULES[type_code]}{asr}

只輸出文章 markdown,不要任何其他說明。
"""
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_prompts.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/prompts.py tests/test_prompts.py
git commit -m "feat: prompt 模板(M5/M6/quick,type 特化集中管理)"
```

---

### Task 8: m5_notes.py(map:分段筆記)

**Files:**
- Create: `src/yt_summary/m5_notes.py`
- Test: `tests/test_m5_notes.py`

**Interfaces:**
- Consumes: `prompts.m5_prompt`、`llm.call_llm`(可注入)、`llm.LLMError`、`llm.LLMResult`。
- Produces: `m5_notes.map_segments(segments, transcript, type_code, model, concurrency, call=llm.call_llm) -> tuple[list[dict], list[LLMResult]]`——notes 依 segment_id 排序;成功 note 帶 `status="ok"`,失敗帶 `status="failed"` 與 `error`。

- [ ] **Step 1: 寫失敗測試 `tests/test_m5_notes.py`**

```python
from yt_summary.llm import LLMError, LLMResult
from yt_summary.m5_notes import map_segments

SEG = lambda i: {"segment_id": i, "start": i * 100.0, "end": i * 100.0 + 90,
                 "chapter_title": None, "context_prefix": "",
                 "sentences": [{"i": 0, "start": i * 100.0, "end": i * 100.0 + 4,
                                "text": "測試句"}],
                 "token_estimate": 3}

TRANSCRIPT = {"video_id": "v", "title": "T", "duration_sec": 400,
              "source": "manual_subs", "language": "zh-TW", "uploader": "",
              "upload_date": "", "webpage_url": "", "chapters": [],
              "sentences": []}


def _result(parsed):
    return LLMResult(text="", parsed=parsed, usage={"input_tokens": 1, "output_tokens": 1},
                     cost_usd=0.01, duration_sec=0.1, model="sonnet")


def test_map_success_and_ordering():
    def call(prompt, model, expect_json=False, **kw):
        # 從 prompt 的 schema 取回 segment_id(prompt 含 "segment_id": N)
        import re
        sid = int(re.search(r'"segment_id": (\d+)', prompt).group(1))
        return _result({"segment_id": sid, "topic": f"t{sid}", "points": []})

    notes, results = map_segments([SEG(1), SEG(0)], TRANSCRIPT, "A", "sonnet",
                                  concurrency=2, call=call)
    assert [n["segment_id"] for n in notes] == [0, 1]
    assert all(n["status"] == "ok" for n in notes)
    assert len(results) == 2


def test_map_partial_failure():
    def call(prompt, model, expect_json=False, **kw):
        if '"segment_id": 1' in prompt:
            raise LLMError("boom")
        return _result({"segment_id": 0, "topic": "t0", "points": []})

    notes, results = map_segments([SEG(0), SEG(1)], TRANSCRIPT, "A", "sonnet",
                                  concurrency=1, call=call)
    assert notes[0]["status"] == "ok"
    assert notes[1] == {"segment_id": 1, "status": "failed", "error": "boom"}
    assert len(results) == 1  # 失敗的呼叫沒有 LLMResult


def test_map_fills_missing_segment_id():
    def call(prompt, model, expect_json=False, **kw):
        return _result({"topic": "模型忘了填 id", "points": []})

    notes, _ = map_segments([SEG(5)], TRANSCRIPT, "A", "sonnet",
                            concurrency=1, call=call)
    assert notes[0]["segment_id"] == 5
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_m5_notes.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/m5_notes.py`**

```python
"""M5 分段筆記(map):每段一次 LLM 呼叫,ThreadPoolExecutor 並發。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import prompts
from .llm import LLMError, LLMResult, call_llm


def map_segments(segments: list[dict], transcript: dict, type_code: str,
                 model: str, concurrency: int,
                 call=call_llm) -> tuple[list[dict], list[LLMResult]]:
    def one(seg: dict) -> tuple[dict, LLMResult | None]:
        prompt = prompts.m5_prompt(seg, transcript, type_code)
        try:
            r = call(prompt, model=model, expect_json=True)
            note = r.parsed if isinstance(r.parsed, dict) else {"points": r.parsed or []}
            note["segment_id"] = note.get("segment_id", seg["segment_id"])
            note["status"] = "ok"
            return note, r
        except LLMError as e:
            return {"segment_id": seg["segment_id"], "status": "failed",
                    "error": str(e)}, None

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        pairs = list(ex.map(one, segments))

    notes = sorted((n for n, _ in pairs), key=lambda n: n["segment_id"])
    results = [r for _, r in pairs if r is not None]
    return notes, results
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_m5_notes.py`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/m5_notes.py tests/test_m5_notes.py
git commit -m "feat: M5 分段筆記 map(並發、單段失敗不中斷)"
```

---

### Task 9: m6_reduce.py(reduce:整合成文)

**Files:**
- Create: `src/yt_summary/m6_reduce.py`
- Test: `tests/test_m6_reduce.py`

**Interfaces:**
- Consumes: `prompts.render_note_block` / `m6_prompt` / `m6_mid_prompt`、`llm.call_llm`(可注入)、`tokens.estimate_tokens`(可注入)。
- Produces: `m6_reduce.reduce_notes(notes, transcript, type_code, model, call=llm.call_llm, estimate=estimate_tokens, mid_reduce_threshold=60000, chunk_size=4) -> tuple[str, list[LLMResult]]`(回傳文章 markdown 與全部 LLM 呼叫結果)。

- [ ] **Step 1: 寫失敗測試 `tests/test_m6_reduce.py`**

```python
from yt_summary.llm import LLMResult
from yt_summary.m6_reduce import reduce_notes

TRANSCRIPT = {"video_id": "v", "title": "T", "duration_sec": 400,
              "source": "manual_subs", "language": "zh-TW", "uploader": "",
              "upload_date": "", "webpage_url": "", "chapters": [], "sentences": []}


def _note(i):
    return {"segment_id": i, "status": "ok", "time_range": [0, 1],
            "topic": f"主題{i}", "points": [], "entities": [],
            "facts_numbers": [], "code_blocks": [], "speaker_emphasis": []}


def _result(text):
    return LLMResult(text=text, parsed=None, usage={"input_tokens": 1, "output_tokens": 1},
                     cost_usd=0.01, duration_sec=0.1, model="opus")


def test_single_reduce():
    calls = []

    def call(prompt, model, **kw):
        calls.append(prompt)
        return _result("# 文章")

    article, results = reduce_notes([_note(0), _note(1)], TRANSCRIPT, "A", "opus", call=call)
    assert article == "# 文章"
    assert len(calls) == 1
    assert "主題0" in calls[0] and "主題1" in calls[0]


def test_failed_segments_mentioned():
    captured = []

    def call(prompt, model, **kw):
        captured.append(prompt)
        return _result("# 文章")

    notes = [_note(0), {"segment_id": 1, "status": "failed", "error": "x"}]
    reduce_notes(notes, TRANSCRIPT, "A", "opus", call=call)
    assert "第 1 段" in captured[0]


def test_mid_reduce_when_over_threshold():
    calls = []

    def call(prompt, model, **kw):
        calls.append(prompt)
        return _result(f"合併稿{len(calls)}")

    # threshold=0 強制走中間 reduce;6 個 note、chunk 4 → 2 次 mid + 1 次 final
    notes = [_note(i) for i in range(6)]
    article, results = reduce_notes(notes, TRANSCRIPT, "A", "opus", call=call,
                                    mid_reduce_threshold=0, chunk_size=4)
    assert len(calls) == 3
    assert article == "合併稿3"
    assert "合併稿1" in calls[2] and "合併稿2" in calls[2]  # final 吃 mid 的輸出
    assert len(results) == 3
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_m6_reduce.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/m6_reduce.py`**

```python
"""M6 整合(reduce):筆記 → 文章;超量時先做中間 reduce(spec §M6)。"""
from __future__ import annotations

from . import prompts
from .llm import LLMResult, call_llm
from .tokens import estimate_tokens


def reduce_notes(notes: list[dict], transcript: dict, type_code: str, model: str,
                 call=call_llm, estimate=estimate_tokens,
                 mid_reduce_threshold: int = 60000,
                 chunk_size: int = 4) -> tuple[str, list[LLMResult]]:
    ok = sorted((n for n in notes if n.get("status") == "ok"),
                key=lambda n: n["segment_id"])
    failed_ids = sorted(n["segment_id"] for n in notes if n.get("status") != "ok")
    blocks = [prompts.render_note_block(n) for n in ok]
    results: list[LLMResult] = []

    if estimate("\n".join(blocks)) > mid_reduce_threshold:
        merged: list[str] = []
        for i in range(0, len(blocks), chunk_size):
            r = call(prompts.m6_mid_prompt(blocks[i:i + chunk_size], transcript, type_code),
                     model=model)
            merged.append(r.text)
            results.append(r)
        blocks = merged

    r = call(prompts.m6_prompt(blocks, transcript, type_code, failed_ids), model=model)
    results.append(r)
    return r.text, results
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_m6_reduce.py`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/m6_reduce.py tests/test_m6_reduce.py
git commit -m "feat: M6 整合 reduce(缺段警告、超量中間 reduce)"
```

---

### Task 10: quick.py(短片單次呼叫)

**Files:**
- Create: `src/yt_summary/quick.py`
- Test: `tests/test_quick.py`

**Interfaces:**
- Consumes: `prompts.quick_prompt`、`llm.call_llm`(可注入)。
- Produces: `quick.quick_summarize(transcript, type_code, model, call=llm.call_llm) -> tuple[str, list[LLMResult]]`。LLMError 不攔截——由 cli 中止(design §8:quick 失敗即中止)。

- [ ] **Step 1: 寫失敗測試 `tests/test_quick.py`**

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_quick.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/quick.py`**

```python
"""quick 模式:短片全逐字稿 + super prompt 單次呼叫(design D1–D3)。"""
from __future__ import annotations

from . import prompts
from .llm import LLMResult, call_llm


def quick_summarize(transcript: dict, type_code: str, model: str,
                    call=call_llm) -> tuple[str, list[LLMResult]]:
    r = call(prompts.quick_prompt(transcript, type_code), model=model)
    return r.text, [r]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_quick.py`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/quick.py tests/test_quick.py
git commit -m "feat: quick 短片模式(單次 super prompt 呼叫)"
```

---

### Task 11: m8_output.py(產物落地 + run.log)

**Files:**
- Create: `src/yt_summary/m8_output.py`
- Test: `tests/test_m8_output.py`

**Interfaces:**
- Consumes: `llm.LLMResult`。
- Produces:
  - `m8_output.RunLog`:`add(step: str, duration_sec: float, note: str = "")`、`add_llm(step: str, duration_sec: float, results: list[LLMResult], note: str = "")`、`render() -> str`
  - `m8_output.write_outputs(outdir: Path, transcript=None, segments=None, notes=None, article=None, runlog=None) -> None`(有給的才寫:`transcript.json`、`segments.json`、`segment_notes/segment_XXX.json`、`article_final.md`、`run.log`)

- [ ] **Step 1: 寫失敗測試 `tests/test_m8_output.py`**

```python
import json

from yt_summary.llm import LLMResult
from yt_summary.m8_output import RunLog, write_outputs


def _result(cost=0.5):
    return LLMResult(text="x", parsed=None,
                     usage={"input_tokens": 100, "cache_creation_input_tokens": 50,
                            "cache_read_input_tokens": 10, "output_tokens": 20},
                     cost_usd=cost, duration_sec=1.0, model="sonnet")


def test_runlog_render():
    log = RunLog()
    log.add("M1 擷取", 3.2)
    log.add_llm("M5 分段筆記", 100.0, [_result(), _result()], note="1 failed")
    out = log.render()
    assert "M1 擷取" in out
    assert "calls=2" in out
    assert "in=320" in out          # (100+50+10)×2
    assert "out=40" in out
    assert "cost=$1.00" in out
    assert "1 failed" in out
    assert "total" in out


def test_write_outputs_full(tmp_path):
    log = RunLog()
    log.add("step", 1.0)
    write_outputs(
        tmp_path,
        transcript={"video_id": "v"},
        segments=[{"segment_id": 0}],
        notes=[{"segment_id": 0, "status": "ok"}],
        article="# 文章",
        runlog=log,
    )
    assert json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8")) == {"video_id": "v"}
    assert json.loads((tmp_path / "segments.json").read_text(encoding="utf-8")) == {"segments": [{"segment_id": 0}]}
    assert (tmp_path / "segment_notes" / "segment_000.json").exists()
    assert (tmp_path / "article_final.md").read_text(encoding="utf-8") == "# 文章"
    assert "step" in (tmp_path / "run.log").read_text(encoding="utf-8")


def test_write_outputs_quick_mode_partial(tmp_path):
    # quick 模式沒有 segments/notes → 不產生對應檔案
    write_outputs(tmp_path, transcript={"video_id": "v"}, article="# a")
    assert not (tmp_path / "segments.json").exists()
    assert not (tmp_path / "segment_notes").exists()
    assert (tmp_path / "article_final.md").exists()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_m8_output.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/m8_output.py`**

```python
"""M8 輸出:中間產物落地 + run.log(耗時、token、成本彙總)。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LLMResult


@dataclass
class LogEntry:
    step: str
    duration_sec: float
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    note: str = ""


@dataclass
class RunLog:
    entries: list[LogEntry] = field(default_factory=list)

    def add(self, step: str, duration_sec: float, note: str = "") -> None:
        self.entries.append(LogEntry(step, duration_sec, note=note))

    def add_llm(self, step: str, duration_sec: float,
                results: list[LLMResult], note: str = "") -> None:
        tin = sum(
            r.usage.get("input_tokens", 0)
            + r.usage.get("cache_creation_input_tokens", 0)
            + r.usage.get("cache_read_input_tokens", 0)
            for r in results
        )
        tout = sum(r.usage.get("output_tokens", 0) for r in results)
        cost = sum(r.cost_usd for r in results)
        self.entries.append(
            LogEntry(step, duration_sec, len(results), tin, tout, cost, note)
        )

    def render(self) -> str:
        lines = ["yt-summary run log", "=" * 64]
        for e in self.entries:
            row = f"{e.step:<16}{e.duration_sec:>9.1f}s"
            if e.calls:
                row += (f"  calls={e.calls} in={e.tokens_in} out={e.tokens_out}"
                        f" cost=${e.cost_usd:.2f}")
            if e.note:
                row += f"  ({e.note})"
            lines.append(row)
        lines.append("-" * 64)
        total_t = sum(e.duration_sec for e in self.entries)
        total_c = sum(e.cost_usd for e in self.entries)
        lines.append(f"{'total':<16}{total_t:>9.1f}s  cost=${total_c:.2f}")
        return "\n".join(lines) + "\n"


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def write_outputs(outdir: Path, transcript=None, segments=None, notes=None,
                  article=None, runlog=None) -> None:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if transcript is not None:
        _dump(outdir / "transcript.json", transcript)
    if segments is not None:
        _dump(outdir / "segments.json", {"segments": segments})
    if notes is not None:
        notes_dir = outdir / "segment_notes"
        notes_dir.mkdir(exist_ok=True)
        for n in notes:
            _dump(notes_dir / f"segment_{n['segment_id']:03d}.json", n)
    if article is not None:
        (outdir / "article_final.md").write_text(article, encoding="utf-8")
    if runlog is not None:
        (outdir / "run.log").write_text(runlog.render(), encoding="utf-8")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_m8_output.py`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/m8_output.py tests/test_m8_output.py
git commit -m "feat: M8 產物落地與 run.log 彙總"
```

---

### Task 12: vault.py 匯出(slug、檔頭、原子寫入)

**Files:**
- Create: `src/yt_summary/vault.py`
- Test: `tests/test_vault_export.py`

**Interfaces:**
- Consumes: transcript 資料契約、`prompts.ts`。
- Produces:
  - `vault.slugify(title: str, max_len: int = 40) -> str`
  - `vault.export_article(article_md: str, transcript: dict, raw_dir: Path, type_code: str, today: date | None = None) -> Path`——檔名 `yt-{YYYYMMDD}-{slug}-{video_id}.md`;寫入前先刪同 video_id 舊檔(重跑覆蓋);`.tmp-` 暫存檔 + `os.replace` 原子寫入;檔頭含來源 URL/頻道/時長/type/產生日期。

- [ ] **Step 1: 寫失敗測試 `tests/test_vault_export.py`**

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_vault_export.py`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 實作 `src/yt_summary/vault.py`(先只做匯出;remove 在 Task 13 追加)**

```python
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

    # 重跑覆蓋語意:先清掉同 video_id 的舊檔(檔名日期可能不同)
    for stale in raw_dir.glob(f"yt-*-{vid}.md"):
        stale.unlink()

    content = _header(transcript, type_code, generated) + article_md
    tmp = raw_dir / f".tmp-{name}"
    target = raw_dir / name
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)  # 原子:ingest 只會看到完整檔或沒有檔
    return target
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest -q tests/test_vault_export.py`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/vault.py tests/test_vault_export.py
git commit -m "feat: vault 匯出(slug 檔名、metadata 檔頭、原子寫入、重跑覆蓋)"
```

---

### Task 13: vault.py remove(事後移除)

**Files:**
- Modify: `src/yt_summary/vault.py`(追加)
- Test: `tests/test_vault_remove.py`

**Interfaces:**
- Produces:
  - `vault.extract_video_id(target: str) -> str`(支援 `v=`、`youtu.be/`、`shorts/`、`live/`、`embed/`、裸 11 碼 id;解析不出 raise `ValueError`)
  - `vault.RemoveReport`(dataclass:`video_id: str`、`removed_output: bool`、`removed_raw: list[str]`、`affected_wiki: list[str]`)
  - `vault.remove(target: str, output_dir: Path, raw_dir: Path, wiki_dir: Path) -> RemoveReport`——刪 `output/{vid}/`、刪 `raw/yt-*-{vid}.md`;grep wiki 各 `.md` 的 `source:` 行是否含 vid,只列出**不修改**。

- [ ] **Step 1: 寫失敗測試 `tests/test_vault_remove.py`**

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_vault_remove.py`
Expected: FAIL,`ImportError`(`extract_video_id` 不存在)

- [ ] **Step 3: 在 `src/yt_summary/vault.py` 追加**

檔頭 import 增加 `import shutil` 與 `from dataclasses import dataclass`,並在檔尾追加:

```python
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
```

- [ ] **Step 4: 跑全部 vault 測試確認通過(含 Task 12 回歸)**

Run: `uv run pytest -q tests/test_vault_export.py tests/test_vault_remove.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yt_summary/vault.py tests/test_vault_remove.py
git commit -m "feat: remove 移除流程(video id 解析、raw 清除、wiki source 偵測)"
```

---

### Task 14: cli.py(進入點與編排)

**Files:**
- Create: `src/yt_summary/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: 前面所有模組的公開介面(`config.load_config`、`m1_fetch.fetch_meta/pick_subtitle_lang/download_subtitle/FetchError`、`m2_clean.*`、`m3_segment.segment`、`m5_notes.map_segments`、`m6_reduce.reduce_notes`、`quick.quick_summarize`、`m8_output.RunLog/write_outputs`、`vault.export_article/remove`、`llm.LLMError`)。
- Produces:
  - `cli.decide_mode(duration_sec: int, mode_arg: str, threshold: int) -> str`
  - `cli.main(argv: list[str] | None = None) -> int`(console entry;`yt-summary <URL> ...` 隱含 run 子指令、`yt-summary remove <target>`)

- [ ] **Step 1: 寫失敗測試 `tests/test_cli.py`**

```python
import json

from yt_summary import cli, m1_fetch, quick


def test_decide_mode():
    assert cli.decide_mode(600, "auto", 900) == "quick"
    assert cli.decide_mode(1200, "auto", 900) == "full"
    assert cli.decide_mode(900, "auto", 900) == "full"    # 邊界:>= threshold 走 full
    assert cli.decide_mode(1200, "quick", 900) == "quick"  # 強制覆寫
    assert cli.decide_mode(600, "full", 900) == "full"


CONFIG_TMPL = """\
defaults: {{ language_out: zh-TW, concurrency: 1, output_dir: {out} }}
modes: {{ quick_threshold_sec: 900 }}
llm:
  models: {{ m5: sonnet, m6: opus, quick: opus }}
vault: {{ export: true, raw_dir: {raw} }}
types:
  A: {{ segment_tokens: [3000, 4000], overlap_sec: 45 }}
"""


def _write_config(tmp_path):
    out = tmp_path / "output"
    raw = tmp_path / "raw"
    raw.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG_TMPL.format(out=out, raw=raw), encoding="utf-8")
    return cfg, out, raw


JSON3 = {"events": [{"tStartMs": 0, "dDurationMs": 3000, "segs": [{"utf8": "哈囉大家好。"}]}]}

META = {"id": "abcdefghijk", "title": "短片", "duration": 300,
        "uploader": "頻道", "upload_date": "20260701",
        "webpage_url": "https://youtu.be/abcdefghijk", "chapters": [],
        "subtitles": {}, "automatic_captions": {"zh-TW": [{"ext": "json3"}]}}


def test_run_quick_end_to_end(tmp_path, monkeypatch):
    cfg, out, raw = _write_config(tmp_path)

    monkeypatch.setattr(m1_fetch, "fetch_meta", lambda url, run=None: META)

    def fake_download(url, lang, source, workdir, run=None):
        p = workdir / "abcdefghijk.zh-TW.json3"
        p.write_text(json.dumps(JSON3), encoding="utf-8")
        return p

    monkeypatch.setattr(m1_fetch, "download_subtitle", fake_download)
    monkeypatch.setattr(quick, "quick_summarize",
                        lambda transcript, t, m, call=None: ("# 文章", []))

    rc = cli.main(["https://youtu.be/abcdefghijk", "--type", "A",
                   "--config", str(cfg)])
    assert rc == 0
    outdir = out / "abcdefghijk"
    assert (outdir / "article_final.md").read_text(encoding="utf-8") == "# 文章"
    assert (outdir / "transcript.json").exists()
    assert (outdir / "run.log").exists()
    exported = list(raw.glob("yt-*-abcdefghijk.md"))
    assert len(exported) == 1                      # vault 匯出
    assert "# 文章" in exported[0].read_text(encoding="utf-8")


def test_run_no_vault_flag(tmp_path, monkeypatch):
    cfg, out, raw = _write_config(tmp_path)
    monkeypatch.setattr(m1_fetch, "fetch_meta", lambda url, run=None: META)

    def fake_download(url, lang, source, workdir, run=None):
        p = workdir / "abcdefghijk.zh-TW.json3"
        p.write_text(json.dumps(JSON3), encoding="utf-8")
        return p

    monkeypatch.setattr(m1_fetch, "download_subtitle", fake_download)
    monkeypatch.setattr(quick, "quick_summarize",
                        lambda transcript, t, m, call=None: ("# 文章", []))

    rc = cli.main(["https://youtu.be/abcdefghijk", "--type", "A",
                   "--config", str(cfg), "--no-vault"])
    assert rc == 0
    assert list(raw.glob("*.md")) == []


def test_run_fetch_error_exits_1(tmp_path, monkeypatch, capsys):
    cfg, _, _ = _write_config(tmp_path)

    def boom(url, run=None):
        raise m1_fetch.FetchError("影片不存在")

    monkeypatch.setattr(m1_fetch, "fetch_meta", boom)
    rc = cli.main(["https://youtu.be/abcdefghijk", "--type", "A",
                   "--config", str(cfg)])
    assert rc == 1
    assert "影片不存在" in capsys.readouterr().err


def test_remove_subcommand(tmp_path, monkeypatch, capsys):
    cfg, out, raw = _write_config(tmp_path)
    # wiki 目錄 = raw 的手足目錄(vault/wiki)
    (raw.parent / "wiki").mkdir(exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "abcdefghijk").mkdir()
    (raw / "yt-20260707-短片-abcdefghijk.md").write_text("x", encoding="utf-8")

    rc = cli.main(["remove", "abcdefghijk", "--config", str(cfg)])
    assert rc == 0
    assert not (out / "abcdefghijk").exists()
    assert list(raw.glob("*.md")) == []
    assert "已完全移除" in capsys.readouterr().out
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest -q tests/test_cli.py`
Expected: FAIL,`ModuleNotFoundError`(cli 不存在)

- [ ] **Step 3: 實作 `src/yt_summary/cli.py`**

```python
"""CLI 進入點:run(隱含)與 remove 兩個子指令。"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import m1_fetch, m2_clean, m3_segment, m5_notes, m6_reduce, quick, vault
from .config import load_config
from .llm import LLMError
from .m8_output import RunLog, write_outputs


def decide_mode(duration_sec: int, mode_arg: str, threshold: int) -> str:
    if mode_arg in ("full", "quick"):
        return mode_arg
    return "quick" if duration_sec < threshold else "full"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yt-summary")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="影片 → 重點文章")
    run.add_argument("url")
    run.add_argument("--type", required=True, choices=["A", "B", "C"], dest="type_code")
    run.add_argument("--mode", default="auto", choices=["auto", "full", "quick"])
    run.add_argument("--no-vault", action="store_true")
    run.add_argument("--config", default="config.yaml")
    run.set_defaults(func=cmd_run)

    rm = sub.add_parser("remove", help="移除已產生的摘要(output + vault/raw)")
    rm.add_argument("target", help="影片 URL 或 11 碼 video id")
    rm.add_argument("--config", default="config.yaml")
    rm.set_defaults(func=cmd_remove)
    return parser


def cmd_run(args) -> int:
    cfg = load_config(Path(args.config))
    runlog = RunLog()

    t = time.monotonic()
    meta = m1_fetch.fetch_meta(args.url)
    picked = m1_fetch.pick_subtitle_lang(meta)
    if picked is None:
        raise m1_fetch.FetchError("無任何字幕(手動/自動皆無)——Whisper fallback 為 Phase 2")
    lang, source = picked
    outdir = cfg.output_dir / meta["id"]
    outdir.mkdir(parents=True, exist_ok=True)
    sub_path = m1_fetch.download_subtitle(args.url, lang, source, outdir)
    runlog.add("M1 擷取", time.monotonic() - t)

    t = time.monotonic()
    cues = m2_clean.dedup_cues(m2_clean.parse_json3(sub_path))
    sentences = m2_clean.split_sentences(cues)
    transcript = m2_clean.build_transcript(meta, sentences, source, lang)
    runlog.add("M2 前處理", time.monotonic() - t)

    mode = decide_mode(transcript["duration_sec"], args.mode, cfg.quick_threshold_sec)
    segments = notes = None
    if mode == "quick":
        t = time.monotonic()
        article, calls = quick.quick_summarize(
            transcript, args.type_code, cfg.llm_models["quick"])
        runlog.add_llm("QUICK 單次呼叫", time.monotonic() - t, calls)
    else:
        tcfg = cfg.types[args.type_code]
        t = time.monotonic()
        segments = m3_segment.segment(transcript, tcfg.segment_tokens, tcfg.overlap_sec)
        runlog.add("M3 切分", time.monotonic() - t, note=f"{len(segments)} 段")

        t = time.monotonic()
        notes, m5_calls = m5_notes.map_segments(
            segments, transcript, args.type_code, cfg.llm_models["m5"], cfg.concurrency)
        n_failed = sum(1 for n in notes if n.get("status") != "ok")
        runlog.add_llm("M5 分段筆記", time.monotonic() - t, m5_calls,
                       note=f"{n_failed} failed" if n_failed else "")

        t = time.monotonic()
        article, m6_calls = m6_reduce.reduce_notes(
            notes, transcript, args.type_code, cfg.llm_models["m6"])
        runlog.add_llm("M6 整合", time.monotonic() - t, m6_calls)

    write_outputs(outdir, transcript=transcript, segments=segments,
                  notes=notes, article=article, runlog=runlog)

    if cfg.vault_export and not args.no_vault:
        try:
            p = vault.export_article(article, transcript, cfg.vault_raw_dir, args.type_code)
            print(f"已匯出 vault:{p}")
        except OSError as e:
            print(f"警告:vault 匯出失敗,已跳過({e})", file=sys.stderr)

    print(f"完成(mode={mode}):{outdir / 'article_final.md'}")
    return 0


def cmd_remove(args) -> int:
    cfg = load_config(Path(args.config))
    wiki_dir = cfg.vault_raw_dir.parent / "wiki"
    report = vault.remove(args.target, cfg.output_dir, cfg.vault_raw_dir, wiki_dir)
    print(f"video_id:{report.video_id}")
    print(f"output/ 移除:{'是' if report.removed_output else '無此目錄'}")
    print(f"vault/raw 移除:{report.removed_raw or '無對應檔案'}")
    if report.affected_wiki:
        print("注意:以下 wiki 筆記的 source 指向此影片(已被 ingest),"
              "請在 vault 的 claude session 依其治理規則處理:")
        for f in report.affected_wiki:
            print(f"  - wiki/{f}")
    else:
        print("wiki 無引用——已完全移除。")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("run", "remove") and not argv[0].startswith("-"):
        argv = ["run"] + argv  # `yt-summary <URL> ...` 隱含 run
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (m1_fetch.FetchError, LLMError, ValueError) as e:
        print(f"錯誤:{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑整套測試確認通過**

Run: `uv run pytest -q`
Expected: 全數 passed(0 failed)

- [ ] **Step 5: 驗證 console script 裝得起來**

Run: `uv run yt-summary --help && uv run yt-summary run --help`
Expected: 兩者都印出 usage,run 子指令含 `--type {A,B,C}`、`--mode`、`--no-vault`

- [ ] **Step 6: Commit**

```bash
git add src/yt_summary/cli.py tests/test_cli.py
git commit -m "feat: CLI 進入點(run/remove 子指令、mode 判斷、pipeline 編排)"
```

---

### Task 15: 收尾(CLAUDE.md 事實區、README、煙霧測試指引)

**Files:**
- Modify: `CLAUDE.md`(專案根;只動事實區佔位符——依 kit-evolution 規則,改動需在回報中明列)
- Modify: `.claude/protected-paths`(只加嚴:新增 vault wiki 禁區)
- Create: `README.md`, `docs/smoke-test.md`

**Interfaces:** 無程式介面;文件任務。

- [ ] **Step 1: 填 `CLAUDE.md` 事實區佔位符**

- Project goal 段:`YouTube 影片轉重點文章的個人 pipeline:長片走 map-reduce、短片單次呼叫,文章自動落地個人知識庫 vault/raw/,由 vault 的 nightly ingest 蒸餾進 wiki。`
- Stack 段:
  - Language: `Python 3.12(uv 管理)`
  - Framework: `none(CLI;LLM 走 headless claude -p)`
  - Datastore: `none(檔案:output/ 中間產物、vault/raw 匯出)`
  - Build/run: `uv run yt-summary <URL> --type A|B|C [--mode auto|full|quick] [--no-vault]`
  - Test: `uv run pytest -q`
- File layout 段(照實際檔案,每檔一句用途):
  ```
  - src/yt_summary/cli.py — 進入點:run/remove 子指令、mode 判斷、pipeline 編排
  - src/yt_summary/config.py — config.yaml 載入(只有 cli 使用)
  - src/yt_summary/m1_fetch.py — yt-dlp metadata + 字幕下載
  - src/yt_summary/m2_clean.py — 字幕去重、斷句 → transcript
  - src/yt_summary/m3_segment.py — 章節/token 窗切分
  - src/yt_summary/m5_notes.py — 分段筆記 map(並發 LLM)
  - src/yt_summary/m6_reduce.py — 筆記整合成文(含中間 reduce)
  - src/yt_summary/quick.py — 短片單次呼叫路徑
  - src/yt_summary/m8_output.py — 產物落地 + run.log
  - src/yt_summary/vault.py — vault/raw 匯出(原子寫入)+ remove
  - src/yt_summary/llm.py — claude -p wrapper(唯一 LLM 入口)
  - src/yt_summary/prompts.py — 全部 prompt 模板(type 特化)
  - src/yt_summary/tokens.py — 啟發式 token 估算
  ```
- Project-specific constraints 段新增一條(加嚴):
  `- /mnt/c/Users/micro/Documents/vault/wiki/:本專案絕不寫入——wiki 由 vault 治理;程式與 AI 都只准 grep。程式僅寫 vault/raw/。`

- [ ] **Step 2: `.claude/protected-paths` 追加一行(加嚴,允許自行新增)**

```
/mnt/c/Users/micro/Documents/vault/wiki/
```

- [ ] **Step 3: 寫 `README.md`**

```markdown
# yt-summary

YouTube 影片 → 重點文章(zh-TW),文章自動落地個人知識庫 `vault/raw/`。

## 需求
- Python 3.12+、uv
- 已登入的 Claude Code CLI(`claude -p` 走訂閱)
- 網路(yt-dlp 抓字幕)

## 使用
```bash
uv run yt-summary "https://youtu.be/VIDEO_ID" --type A          # A=AI 談話 B=財經 C=coding
uv run yt-summary "https://..." --type B --mode full            # 強制完整 pipeline
uv run yt-summary "https://..." --type A --no-vault             # 不匯出 vault
uv run yt-summary remove VIDEO_ID_或_URL                        # 事後移除
```

- 短片(< 15 分鐘)自動走 quick 單次呼叫;長片走 M3→M5→M6 map-reduce。
- 產物:`output/{video_id}/`(article_final.md、transcript.json、run.log …)。
- 中途 Ctrl+C 安全:vault 匯出是最後一步且原子寫入。
- 設計文件:`docs/specs/2026-07-07-yt-summary-v1-design.md`。
```

- [ ] **Step 4: 寫 `docs/smoke-test.md`(手動煙霧測試,需網路與訂閱額度)**

```markdown
# 煙霧測試(手動,每次大改後跑)

1. **quick 路徑**:挑一支 < 15 分鐘、有字幕的影片
   `uv run yt-summary "<URL>" --type A`
   驗收:exit 0;output/{id}/ 有 transcript.json、article_final.md、run.log(無 segments);
   vault/raw 出現 yt-*.md 且檔頭含來源 URL;文章有 TL;DR 與 [mm:ss] 時間戳。
2. **full 路徑**:挑一支 30–40 分鐘 Type A/B 影片
   `uv run yt-summary "<URL>" --type B`
   驗收:segments.json 與 segment_notes/ 齊全;run.log 各步驟有 tokens/cost;
   Type B 文章附錄含數字彙整表。
3. **remove**:`uv run yt-summary remove <上面用的 id>`
   驗收:output 與 vault/raw 檔案消失;回報「已完全移除」(尚未被 ingest 時)。
4. **留存率**(spec §11):對一支你完整看過的影片列 15–20 條 golden list,
   對照文章命中 ≥ 85%;Type B 數字類 100% 原樣。
```

- [ ] **Step 5: 全套測試最後回歸**

Run: `uv run pytest -q`
Expected: 全數 passed

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md .claude/protected-paths README.md docs/smoke-test.md
git commit -m "docs: 收尾——CLAUDE.md 事實區、README、煙霧測試指引、wiki 禁區加嚴"
```

---

## 完成定義(整個計畫)

1. `uv run pytest -q` 全綠(約 40+ 測試)。
2. `uv run yt-summary --help` / `run --help` / `remove --help` 正常。
3. 手動煙霧測試(docs/smoke-test.md)1–3 通過;第 4 項留存率由使用者驗證。
4. 依 kit-workflow:宣告完成前對本輪改動跑 `/kit-review`(cross-model)。
