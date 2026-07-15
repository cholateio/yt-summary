# LESSONS

> 教訓紀錄。格式見 `.claude/rules/kit-evolution.md`（四行結構）。

### 2026-07-15 yt-dlp 字幕 429:缺 curl_cffi 無法 impersonate
- Context: `uv run yts <url>` 抓字幕,metadata 成功但字幕下載炸 HTTP 429。
- Error: `The extractor specified to use impersonation ... but no impersonate target is available` 緊接 `HTTP Error 429: Too Many Requests`。metadata(`--dump-json`)同一次跑卻成功。
- Solution: YouTube 的 caption/timedtext 端點要求瀏覽器 TLS 指紋(impersonation),venv 沒裝 `curl_cffi` → 明碼請求被 429。`uv add curl_cffi` 後 impersonate target 出現、字幕正常下載;程式無需加 `--impersonate` flag,yt-dlp 偵測到即自動用。
- Rule: yt-dlp 打 YouTube 一定要裝 curl_cffi;metadata 成功但字幕/特定端點 429 = impersonation 缺失,不是 IP 被封或 transient rate-limit。

### 2026-07-15 裝了 curl_cffi 仍 429:翻譯字幕軌(tlang)被限流
- Context: 修完 curl_cffi 後,英文影片(How I'd Learn AI Engineering)抓 zh-Hant 字幕仍 429。
- Error: 同影片同時刻,`en` 原生自動軌連打 6 發全過(`......`),`zh-Hant` 翻譯軌 `XXXX..` 幾乎全 `HTTP 429`;交錯打 `.X.X.X.X.X..`——原生每發都過、翻譯幾乎全擋。yt-dlp `--retries`/`--retry-sleep` 不覆蓋字幕下載的 429(無 Retrying 直接失敗)。
- Solution: 根因是 YouTube 對「自動翻譯」端點(`timedtext?...&tlang=`)獨立且激進限流,原生 ASR 軌不受限。改 `pick_subtitle_lang`:人工 > `meta['language']` 原生自動軌 > 翻譯軌(最後手段);翻譯交給 LLM 品質也更好。殘留 429 由 `download_subtitle` 應用層 429 退避重試兜底。
- Rule: 診斷「字幕 429」先分軌實測——原生軌過而翻譯軌擋 = tlang 端點限流,選原生軌+LLM 翻,別跟翻譯端點硬幹;IP 級限流的判準是「連原生軌也擋」。
