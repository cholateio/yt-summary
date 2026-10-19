# Development

## Commands

| Command | Purpose |
|---|---|
| `uv sync` | Create the venv and install dependencies, including dev |
| `uv run yts <URL>` | Video → article (default type A, mode auto) |
| `uv run yts <URL> --type B\|C` | B = finance, C = coding; A is the default |
| `uv run yts <URL> --mode full\|quick` | Force a mode (auto picks quick under 10 minutes) |
| `uv run yts <URL> --no-vault` | Skip the notes-folder export |
| `uv run yts <URL> --quiet` | Silence progress output on stderr |
| `uv run yts remove <VIDEO_ID or URL>` | Remove a run (`output/` + exported file); notes in the sibling `wiki/` are only listed |
| `uv run pytest -q` | The quality gate. Every external service is mocked, so it uses no Claude quota |

`yt-summary` is kept as an equivalent entry point name for `yts`.

The manual smoke test, which needs network access and Claude usage, is in `docs/smoke-test.md`.

## Types

`--type` changes the prompt rules (`TYPE_RULES` in `prompts.py`), the appendix, and the segment size (`config.yaml`).

| Type | For | Prompt rule | Appendix | Segments |
|---|---|---|---|---|
| A | AI, talks, opinion | Keep the speaker's reasoning, not just conclusions | Tools/resources mentioned | 3000–4000 tokens, 45 s overlap |
| B | Finance, investing | Copy numbers, percentages, dates, tickers and indicator names verbatim | Required: table of figures (value, meaning, timestamp) | 3000–4000 tokens, 45 s overlap |
| C | Coding, tutorials | Keep code, file names, function names and command arguments verbatim | Required: full code blocks, each with a timestamp | 2000–3000 tokens, 30 s overlap |

## Modes

| Mode | Behaviour |
|---|---|
| auto (default) | `< 600 s` → quick, `>= 600 s` → full |
| quick | One call: full transcript + one prompt (TL;DR 3–6 items, opus). Fast and light on quota; long videos lose points |
| full | Map-reduce: segment (M3) → per-segment notes (M5, sonnet, concurrency 2) → merge (M6, opus, TL;DR 5–8 items). Slower, higher retention |

Quick on a long video does not fail technically: a 19-minute video produced a quick prompt of about 7k tokens (roughly 370 tokens per minute). The cost is quality, since one call has to digest the whole video.

## Configuration

`config.yaml` holds the defaults (output language, concurrency, output directory, quick threshold, models per stage, per-type segmenting). A sibling `config.local.yaml` (gitignored) is deep-merged over it for machine-specific values. The only one today is `vault.raw_dir`, the export folder; `~` is expanded. Unset means export is skipped with a warning.

There are no environment variables or API keys. LLM calls go through `claude -p`; if the CLI is not signed in, every call exits non-zero and the pipeline reports `錯誤:claude -p …`.

## Progress output

Progress goes to stderr; stdout carries only the final usage summary and output paths, so piping stays clean. Without a TTY, lines are not rewritten with `\r`.

```
抓取影片資訊… ✓ 「影片標題」(20:00) → 模式 full
[1/4] 下載字幕(zh,自動)… ✓
[2/4] 前處理… ✓ 400 句
[3/4] 分段筆記 4 段(sonnet,並發 2)… 3/4
      ⚠ claude -p 失敗,30s 後重試(1/1):…
      ⚠ 第 2 段失敗,該段內容將缺漏:…
      ✓ 3/4 段成功,1 段失敗
[4/4] 整合成文(opus)… ✓
```

A single failed M5 segment does not stop the run (by design); its content is missing from the article, which notes the gap at the top. A failed quick call aborts the run.

## Gotchas

- The quick/full boundary is 600 seconds (`quick_threshold_sec`); exactly 600 goes to full.
- The export is the last step and is atomic (written as `.tmp-*`, then renamed; older files for the same video are removed only after the new one lands). Ctrl+C mid-run never leaves a partial file in the export folder.
- `--tools ""` is deliberate: it gives `claude -p` no tools at all, which is stricter than `--allowedTools ""`.
- Concurrency defaults to 2 because `claude -p` shares the subscription rate limit. Think before raising it.
- All LLM calls go through `llm.call_llm`; modules never spawn `claude` themselves.
- Unit tests never call the real yt-dlp or Claude CLI; fakes are injected.
- The program never writes to the `wiki/` folder beside the export folder. `remove` only lists notes there that cite the video.
- Subtitle priority: human subtitles in `zh-TW`, `zh-Hant`, `zh`, `en`; then the auto track in the video's native language; translated auto tracks last (that endpoint is heavily rate-limited). If Japanese is ever added, `convert.py` needs a guard, because OpenCC `s2twp` rewrites some Japanese kanji.

## Design documents

- `docs/specs/2026-07-07-yt-summary-v1-design.md`: v1 design (authoritative, decisions D1–D7).
- `docs/specs/yt-summary-spec.md`: original spec v0.1; the v1 design wins on conflicts.
