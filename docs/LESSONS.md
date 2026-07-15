# LESSONS

> 教訓紀錄。格式見 `.claude/rules/kit-evolution.md`（四行結構）。

### 2026-07-15 yt-dlp 字幕 429:缺 curl_cffi 無法 impersonate
- Context: `uv run yts <url>` 抓字幕,metadata 成功但字幕下載炸 HTTP 429。
- Error: `The extractor specified to use impersonation ... but no impersonate target is available` 緊接 `HTTP Error 429: Too Many Requests`。metadata(`--dump-json`)同一次跑卻成功。
- Solution: YouTube 的 caption/timedtext 端點要求瀏覽器 TLS 指紋(impersonation),venv 沒裝 `curl_cffi` → 明碼請求被 429。`uv add curl_cffi` 後 impersonate target 出現、字幕正常下載;程式無需加 `--impersonate` flag,yt-dlp 偵測到即自動用。
- Rule: yt-dlp 打 YouTube 一定要裝 curl_cffi;metadata 成功但字幕/特定端點 429 = impersonation 缺失,不是 IP 被封或 transient rate-limit。
