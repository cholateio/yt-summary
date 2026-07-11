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
uv run yts "https://youtu.be/VIDEO_ID"
```

**只要記上面那一行。** type 預設 A(AI/談話)、mode 預設 auto(依片長自選)、自動匯出 vault。
其餘都是例外才用:

| 指令 | 用途 |
|------|------|
| `uv run yts <URL>` | 影片 → 文章(預設 type A、mode auto) |
| `uv run yts <URL> --type B\|C` | 換 type(B=財經 C=coding);A 是預設,不用打 |
| `uv run yts <URL> --mode full\|quick` | 強制指定模式(預設 auto:<10min 走 quick) |
| `uv run yts <URL> --no-vault` | 不匯出 vault |
| `uv run yts <URL> --quiet` | 關閉進度輸出(進度走 stderr,stdout 只有最終摘要與路徑) |
| `uv run yts remove <VIDEO_ID或URL>` | 事後移除(output + vault/raw;wiki 只列不動) |
| `uv run pytest -q` | 唯一的 quality gate(mock 一切外部服務,不吃額度) |

舊指令名 `yt-summary` 仍等價可用(pyproject 保留兩個 entry point),但 `yts` 比較短。

## 🎛️ type 與 mode(唯二要決定的參數)

### `--type`(選填,**預設 A**)——決定 prompt 特化、附錄、切分粒度

| type | 用在 | prompt 特化(`prompts.py` TYPE_RULES) | 附錄 | 切分(`config.yaml`) |
|------|------|--------------------------------------|------|---------------------|
| **A** | AI / 談話 / 觀點 | 保留論點的**推理鏈**——不只記結論,也記講者「為什麼」這樣主張 | 工具/資源清單 | 3000–4000 token,重疊 45s |
| **B** | 財經 / 投資 | 數字、百分比、日期、股票代號、指標名**原樣抄錄**,禁止改寫成「大約」「不錯」 | **必含**數字彙整表(數值｜說明｜時間戳) | 3000–4000 token,重疊 45s |
| **C** | coding / 教學 | 程式碼、檔名、函式名、指令參數**原樣保留**;口述的實作步驟不得簡化 | **必含**完整程式碼區塊(每塊標時間戳) | 2000–3000 token,重疊 30s |

猶豫就不用打——預設就是 A,它最通用,只是不會特別保護數字或程式碼。

### `--mode`(選填,預設 auto)

| mode | 行為 |
|------|------|
| **auto**(預設) | 依片長自動選:`< 600s`(10 分)走 quick,`>= 600s` 走 full |
| **quick** | 單次呼叫:完整逐字稿 + super prompt 一次產文(TL;DR 3–6 條,opus)。快、省額度;長片會漏重點 |
| **full** | map-reduce:M3 切分 → M5 分段筆記(sonnet,並發 2)→ M6 整合(opus,TL;DR 5–8 條)。慢、吃額度;資訊留存高 |

何時該手動覆寫:**短片但資訊密**(講很快、乾貨多)→ `--mode full`;**長片但只想抓個大概** →
`--mode quick`。長片走 quick 不會技術性失敗——實測 19min 影片的 quick prompt 才約 7k tokens
(約 370 tokens/分鐘,3 小時的片也塞得下)——代價純粹是**品質**:單次呼叫要一口氣消化全片,
論點留存率遠低於 map-reduce。省額度換留存率,自己權衡。

## 🔑 憑證(無 .env)

不用 API key——LLM 走 `claude -p`(Claude Code 訂閱),yt-dlp 抓公開字幕。
沒登入 claude CLI 會怎樣:每次 LLM 呼叫 exit 非零,pipeline 回報「錯誤:claude -p …」。

## ☁️ 部署

- 無部署——本機 CLI 工具(WSL)。
- 輸出:`output/{video_id}/`(中間產物可追溯)+ `vault/raw/`(進知識庫)。

---

## 📟 執行時看得到什麼

進度走 **stderr**(stdout 只留最終的用量摘要與產物路徑,pipe 出去不會被污染),
`--quiet` 可關掉。非 TTY(重導向到檔案)時不用 `\r` 覆寫,不會塞控制字元。

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

那兩行 `⚠` 是重點:**M5 單段失敗不會中斷整支**(design),失敗的段落內容就這樣
少掉了。以前它只躺在 `run.log` 裡,你會以為全數成功。現在它當場出聲。

## 🧠 半年後最容易忘的事

- quick/full 的分界是 **600 秒**(`config.yaml` 的 `quick_threshold_sec`),邊界值走 full。
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
