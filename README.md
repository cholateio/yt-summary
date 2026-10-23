# yt-summary

**English** | [繁體中文](README.zh-TW.md)

You find a long YouTube talk or tutorial you would rather read than watch. Run one command with its URL and get a structured article in Traditional Chinese, with a TL;DR, timestamped sections and an appendix, saved as Markdown and optionally dropped into your own notes folder.

```markdown
# 從 Vibe Coding 到 Agentic Engineering:Google Agentic Engineering 課程 Day 1 精華

## TL;DR

- **兩端最大的分水嶺是「驗證」**。沒有 tests(驗證確定性)和 evals(驗證非確定性),不管 prompt 寫得多精緻,做的都還是 vibe coding。[2:48](#)
- **Agent = Model + Harness**。一顆 raw model 不是 agent;你在 Claude Code、Cursor、Codex 感受到的行為差異,很大一部分是 harness 決定的,不是底下那顆 model。[8:13](#)
…
## 一、一條光譜,而不是一個開關
## 二、Context Engineering:通往 agentic engineering 的橋
…
## 附錄
```

- **Three video types**: `--type A` (talks, the default) keeps the speaker's chain of reasoning, `B` (finance) copies numbers, dates and tickers verbatim and appends a table of figures with timestamps, and `C` (coding) keeps code, file names and commands verbatim and appends the code blocks.
- **Two depths**: videos under 10 minutes are written in one Claude call; longer ones are cut into overlapping segments, noted two at a time by Sonnet, and merged into one article by Opus. `--mode quick` or `--mode full` overrides the choice.
- **Subtitles, not audio**: the transcript comes from the video's own subtitles, human-made Chinese or English first, then the auto-generated track in the spoken language, and the result is converted to Taiwan Traditional Chinese with OpenCC, leaving code blocks untouched.
- **Notes-folder export**: the article is also written atomically into a folder you choose, with the source URL, channel and length in its header, and `yts remove <id>` deletes it again.

Input and output for one run:

```
uv run yts "https://youtu.be/<video-id>" --type B
```

```
output/<video-id>/
  transcript.json  segments.json  segment_notes/  article_final.md  run.log
<your notes folder>/yt-<date>-<title>-<video-id>.md
```

A video with no subtitles at all fails; there is no speech-to-text fallback.

## How it works

```
YouTube URL ──► yt-dlp: metadata + subtitles ──► cleaned, timestamped sentences
                                                          │
          under 10 min: one call    10 min or more: segment notes ──► merge
                                                          │
         claude -p (no tools) ──► Markdown ──► output/<id>/ + your notes folder
```

There is no API key and no server. Every model call goes through your own signed-in Claude Code CLI.

## Install

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and [Claude Code](https://claude.com/claude-code) signed in to your account. Each run uses your Claude usage.

1. Clone the repo and run `uv sync`.
2. Run `claude` once and sign in, if you have not already.
3. Optional: to export into a notes folder, create `config.local.yaml` next to `config.yaml`. Without it, articles stay in `output/` and the run prints a warning.
   ```yaml
   vault:
     raw_dir: ~/notes/raw
   ```
4. Run `uv run yts "<youtube-url>"`, adding `--type B` or `--type C` for finance or coding videos.

`yts remove` needs the notes folder from step 3. It also lists notes in a `wiki` folder beside it whose `source:` line points at the video, without changing them.

## Privacy & security

- The transcript and prompts are sent to Anthropic through your Claude Code CLI. yt-dlp's requests to YouTube are the only other traffic.
- Claude runs with every tool disabled (`--tools ""`), so it can only return text. It cannot read your files, run commands or browse.
- The tool stores no keys. Sign-in is handled by Claude Code.
- Output stays on your machine: `output/` is gitignored, and the export only writes inside the folder you configure.

## License

[MIT](LICENSE).
