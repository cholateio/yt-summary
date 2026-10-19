# yt-summary

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

## Constraints

- vault 的 `wiki/`（`vault.raw_dir` 的手足目錄；raw_dir 設在 gitignored 的 `config.local.yaml`，見 config.yaml 註解）：本專案絕不寫入——wiki 由 vault
  自己的治理規則管理；程式與 AI 都只准 grep（remove 子指令僅列出受影響筆記）。
  程式僅寫 `vault/raw/`（原子寫入）。
- 所有 LLM 呼叫必須走 `llm.call_llm`，不准各模組自行 subprocess claude。
- 單元測試不得呼叫真實 yt-dlp / claude CLI（一律注入 fake）。

- Path-type constraints are mirrored in `kit.toml [protected]`; keep the two in sync (one glob per line).
  （vault `wiki/` 在 repo 之外，無法列進 repo-relative 的 `kit.toml`；靠上面的規則與程式只寫 raw_dir 執行。）

## Conventions

- Conventional commits（`type(scope): 摘要`）；commit 前跑 `uv run pytest -q`。
- 本機路徑（vault 位置等）只放 gitignored 的 `config.local.yaml`，tracked 的 `config.yaml` 只放預設與註解。
- GitHub Actions: top-level `permissions: contents: read`, raised per job only when needed.
- GitHub Actions: pin every `uses:` to a 40-character commit SHA with a trailing `# vX.Y.Z` comment.

## Where to look

- `docs/specs/` — 需求權威（`2026-07-07-yt-summary-v1-design.md` 優先於 `yt-summary-spec.md`）
- `docs/DEVELOPMENT.md` — 指令、設定、gotchas
- `docs/smoke-test.md` — 手動煙霧測試（需網路與訂閱額度）
- `docs/architecture/overview.svg` — 架構總覽
