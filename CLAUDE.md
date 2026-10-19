# yt-summary

> CLAUDE.md（kit v4.2）。本檔只放「這個專案是什麼」——工作流、派工、
> review 規則由 `.claude/rules/` 自動載入（kit-owned，別在專案裡改）。

## Project goal

YouTube 影片轉重點文章的個人 pipeline：長片走 map-reduce（M3→M5→M6）、
短片（<10min）單次 super prompt 呼叫；文章自動落地個人知識庫 vault/raw/，
由 vault 的 nightly ingest 蒸餾進 wiki。權威需求：`docs/specs/`（v1 設計
`2026-07-07-yt-summary-v1-design.md` 優先於原始 spec v0.1）。

## Stack

- Language: Python 3.12（uv 管理）
- Framework: none（CLI；LLM 走 headless `claude -p`，訂閱內）
- Datastore: none（檔案：`output/` 中間產物、vault/raw 匯出）
- Build/run: `uv run yts <URL> [--type A|B|C]（預設 A）[--mode auto|full|quick] [--no-vault]`
  （`yt-summary` 為等價舊名）
- Test: `uv run pytest -q`

## File layout

- `src/yt_summary/cli.py` — 進入點：run/remove 子指令、mode 判斷、pipeline 編排
- `src/yt_summary/config.py` — config.yaml 載入（只有 cli 使用，其他模組收明確參數）
- `src/yt_summary/m1_fetch.py` — yt-dlp metadata + 字幕下載
- `src/yt_summary/m2_clean.py` — 字幕去重、斷句 → transcript
- `src/yt_summary/m3_segment.py` — 章節/token 窗切分
- `src/yt_summary/m5_notes.py` — 分段筆記 map（並發 LLM）
- `src/yt_summary/m6_reduce.py` — 筆記整合成文（含中間 reduce）
- `src/yt_summary/quick.py` — 短片單次呼叫路徑
- `src/yt_summary/convert.py` — opencc 確定性簡→繁（s2twp），保留 code 區塊
- `src/yt_summary/progress.py` — 執行期進度輸出（stderr；`--quiet` 關閉）
- `src/yt_summary/m8_output.py` — 產物落地 + run.log
- `src/yt_summary/vault.py` — vault/raw 匯出（原子寫入）+ remove
- `src/yt_summary/llm.py` — claude -p wrapper（唯一 LLM 入口）
- `src/yt_summary/prompts.py` — 全部 prompt 模板（type 特化）
- `src/yt_summary/tokens.py` — 啟發式 token 估算
- `tests/` — 單元/整合測試（mock subprocess 與 LLM，不打真服務）
- `docs/smoke-test.md` — 手動煙霧測試（需網路與訂閱額度）

## Project-specific constraints（禁區與硬規則）

- vault 的 `wiki/`（`vault.raw_dir` 的手足目錄；raw_dir 設在 gitignored 的 `config.local.yaml`，見 config.yaml 註解）：本專案絕不寫入——wiki 由 vault
  自己的治理規則管理；程式與 AI 都只准 grep（remove 子指令僅列出受影響筆記）。
  程式僅寫 `vault/raw/`（原子寫入）。
- 所有 LLM 呼叫必須走 `llm.call_llm`，不准各模組自行 subprocess claude。
- 單元測試不得呼叫真實 yt-dlp / claude CLI（一律注入 fake）。

**同步執法**：上面每一條「路徑型」禁區，都要把路徑同步加進
`.claude/protected-paths`（一行一個 glob，`*` 會跨目錄層級，
`src/legacy/` 結尾斜線代表整棵子樹）——PreToolUse hook 會物理擋下
對這些路徑的編輯，不再只靠模型自律。放寬或刪除任何一條需要 user
明確同意（見 kit-evolution 規則）。

## 檔案路由（需要時才讀，不用背）

| 情境 | 讀這裡 |
|------|--------|
| 卡關了 / 想宣告完成 / 猶豫要不要問 user | `.claude/docs/judgment-matrix.md` |
| 要派工給 subagent | `/kit-dispatch` skill（五種模板） |
| 要記教訓 / 查歷史教訓 / 想改 harness 檔案 | `docs/LESSONS.md`（append；動大手術前先掃一眼）/ kit-evolution 規則（自動已載入） |
| 有 spec 的功能 | `docs/specs/`（spec 是需求的唯一權威來源） |
| 要做 UI / 設計 schema / 同一 bug 連續卡 / 引入外部服務 / 定架構 | `.claude/docs/verification-signals.md`（命中哪節讀哪節） |

（review / isolation / 任務 sizing / 派工升降級 / 判斷層的規則不在
本檔——`.claude/rules/` 的 kit-workflow、kit-delegation、kit-evolution、
kit-judgment 已自動載入每個 session，直接遵守即可。）
