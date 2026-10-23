# yt-summary

[English](README.md) | **繁體中文**

找到一支很長的 YouTube 演講或教學，比起看完，你寧可用讀的。帶著網址跑一行指令，就會得到一篇結構化的繁體中文文章，有 TL;DR、標上時間戳的段落和附錄，存成 Markdown，也可以順便放進你自己的筆記資料夾。

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

- **三種影片類型**：`--type A`（演講，預設）保留講者的推論脈絡；`B`（財經）原樣照抄數字、日期和股票代號，並在文末附上標有時間戳的數字一覽表；`C`（程式）原樣保留程式碼、檔名和指令，並在文末附上程式碼區塊。
- **兩種深度**：10 分鐘以下的影片用一次 Claude 呼叫寫完；較長的影片會切成彼此重疊的片段，由 Sonnet 每次兩段地做筆記，再由 Opus 合併成一篇文章。可以用 `--mode quick` 或 `--mode full` 強制指定。
- **用字幕，不聽音訊**：逐字稿取自影片本身的字幕，優先用人工製作的中文或英文字幕，其次是影片語言的自動產生字幕；結果再用 OpenCC 轉成台灣繁體中文，程式碼區塊不會被動到。
- **匯出到筆記資料夾**：文章也會以原子寫入的方式存進你指定的資料夾，開頭附上來源網址、頻道和影片長度；`yts remove <id>` 可以再把它刪掉。

一次執行的輸入與輸出：

```
uv run yts "https://youtu.be/<video-id>" --type B
```

```
output/<video-id>/
  transcript.json  segments.json  segment_notes/  article_final.md  run.log
<your notes folder>/yt-<date>-<title>-<video-id>.md
```

完全沒有字幕的影片會直接失敗，沒有語音轉文字的備案。

## 它怎麼運作

```
YouTube URL ──► yt-dlp：影片資訊 + 字幕 ──► 清理過、附時間戳的句子
                                                │
     不到 10 分鐘：一次呼叫    10 分鐘以上：分段筆記 ──► 合併
                                                │
    claude -p（不開工具） ──► Markdown ──► output/<id>/ + 你的筆記資料夾
```

不需要 API key，也沒有伺服器。每一次模型呼叫都透過你自己已登入的 Claude Code CLI。

## 安裝

需要：Python 3.12 以上、[uv](https://docs.astral.sh/uv/)，以及登入你帳號的 [Claude Code](https://claude.com/claude-code)。每次執行都會用到你的 Claude 用量。

1. Clone 本 repo，執行 `uv sync`。
2. 如果還沒登入過，先執行一次 `claude` 並登入。
3. 選用：要匯出到筆記資料夾，就在 `config.yaml` 旁邊建立 `config.local.yaml`。沒有這個檔案的話，文章只會留在 `output/`，執行時也會印出警告。
   ```yaml
   vault:
     raw_dir: ~/notes/raw
   ```
4. 執行 `uv run yts "<youtube-url>"`；財經或程式影片再加上 `--type B` 或 `--type C`。

`yts remove` 需要第 3 步設定的筆記資料夾。它也會列出旁邊 `wiki` 資料夾裡 `source:` 那一行指向這支影片的筆記，但不會修改它們。

## 隱私與安全

- 逐字稿和 prompt 會透過你的 Claude Code CLI 送到 Anthropic。除此之外，唯一的對外連線是 yt-dlp 對 YouTube 的請求。
- Claude 執行時所有工具都被停用（`--tools ""`），所以它只能回傳文字，無法讀取你的檔案、執行指令或上網。
- 這個工具不儲存任何 key，登入由 Claude Code 處理。
- 產出只留在你的電腦上：`output/` 已被 gitignore，匯出也只會寫進你設定的資料夾裡。

## 授權

[MIT](LICENSE)。
