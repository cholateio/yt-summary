# yt-summary

> YouTube 影片轉重點文章(zh-TW)的個人 pipeline,文章自動落地個人知識庫
> `vault/raw/`,由 vault 的 nightly ingest 蒸餾進 wiki。**私人 repo,這份
> README 是寫給未來的我**——隔幾個月回來能 30 秒內重啟、想起這專案怎麼
> 運作、以及怎麼叫 AI 接手。
>
> Stack 一行:Python 3.12 · uv · yt-dlp · headless `claude -p`(訂閱內,無 API key)。

---

## 🚀 30 秒重啟

```bash
uv sync                        # 建 venv + 裝依賴(含 dev)
# 確認 claude CLI 已登入(claude -p 走 Claude Code 訂閱)
uv run yt-summary "https://youtu.be/VIDEO_ID" --type A
```

其他指令:

| 指令 | 用途 |
|------|------|
| `uv run yt-summary <URL> --type A\|B\|C` | 影片 → 文章(A=AI 談話 B=財經 C=coding) |
| `uv run yt-summary <URL> --type A --mode full\|quick` | 強制指定模式(預設 auto:<15min 走 quick) |
| `uv run yt-summary <URL> --type A --no-vault` | 不匯出 vault |
| `uv run yt-summary remove <VIDEO_ID或URL>` | 事後移除(output + vault/raw;wiki 只列不動) |
| `uv run pytest -q` | 唯一的 quality gate(mock 一切外部服務,不吃額度) |

## 🔑 憑證(無 .env)

不用 API key——LLM 走 `claude -p`(Claude Code 訂閱),yt-dlp 抓公開字幕。
沒登入 claude CLI 會怎樣:每次 LLM 呼叫 exit 非零,pipeline 回報「錯誤:claude -p …」。

## ☁️ 部署

- 無部署——本機 CLI 工具(WSL)。
- 輸出:`output/{video_id}/`(中間產物可追溯)+ `vault/raw/`(進知識庫)。

---

## 🧠 半年後最容易忘的事

- quick/full 的分界是 **900 秒**(`config.yaml` 的 `quick_threshold_sec`),邊界值走 full。
- vault 匯出是 pipeline **最後一步**且原子寫入(先 `.tmp-` 再 rename,成功後才清舊檔)——中途 Ctrl+C 不會污染 vault。
- vault/raw 的檔案要等**隔天凌晨** ingest 才進 wiki;反悔窗內 `remove` 一刀清乾淨。
- `--tools ""` 是刻意的:讓 claude -p 完全無工具(比 `--allowedTools ""` 更強)。
- M5 單段失敗不中斷(文章開頭會註明缺段);quick 失敗則整支中止。
- 並發預設 2——claude -p 吃訂閱 rate limit,調高前先想清楚。

## 📚 文件地圖

| 檔案 | 內容 |
|------|------|
| `CLAUDE.md` | AI 協作規則 + 本專案 constraints(vault/wiki 禁區) |
| `docs/specs/2026-07-07-yt-summary-v1-design.md` | v1 設計(權威,D1–D7 決策) |
| `docs/specs/yt-summary-spec.md` | 原始 spec v0.1(衝突時以 v1 設計為準) |
| `docs/superpowers/plans/2026-07-07-yt-summary-v1.md` | 實作計畫(15 任務,含完整程式碼) |
| `docs/smoke-test.md` | 手動煙霧測試(需網路與訂閱額度) |

---

## 🤖 叫 AI 接手

**回來第一句(複習 prompt)**
```
先讀 CLAUDE.md 和 docs/specs/2026-07-07-yt-summary-v1-design.md,然後用三五句話跟我複習:
這個專案在做什麼、有哪些必知 constraints、目前有沒有半成品或 TODO。
先不要改任何檔案。
```

**kit 更新**(拉取 kit repo 最新的 workflow rules / templates):
```bash
~/.multi-agent-kit/init.sh . --update
```
