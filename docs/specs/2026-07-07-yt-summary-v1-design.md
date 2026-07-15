# yt-summary v1 設計文件

版本:v1.0(定案)
日期:2026-07-07
關係:本文件是 [yt-summary-spec.md](yt-summary-spec.md)(v0.1)的實作設計,
記錄 v1 範圍裁定與兩項新增能力(短影片模式、vault 整合)。需求衝突時以本文件為準。

---

## 1. 決策記錄

| # | 決策 | 內容 | 理由 |
|---|------|------|------|
| D1 | 短影片模式(quick) | 短片仍走 M1/M2 抓字幕,完整逐字稿 + super prompt 單次 LLM 呼叫;跳過 M3/M5/M6 | 與長流程共用 80% 程式碼、可控、保留時間戳 |
| D2 | 模式選擇 | `duration < 600s` 自動走 quick,`--mode full\|quick` 可強制覆寫 | 預設零負擔,短而密的影片留逃生門。門檻取 10 分鐘:使用者願意親自看完的長度,不值得動用 map-reduce(2026-07-11 由 900s 下修) |
| D3 | quick 的 type 規則 | super prompt 依 `--type` 嵌入特化指令(B:數字原樣、C:程式碼轉錄),但一律不抽畫格 | prompt 差異便宜;畫格是成本大頭,要畫格用 `--mode full`(Phase 3 後) |
| D4 | vault 整合 | 跑完把 `article_final.md` 複製到 `vault/raw/`,由既有 nightly ingest 蒸餾進 wiki | 零新增整合邏輯,完全尊重 vault 治理(raw 只進不改、wiki 存沉澱知識) |
| D5 | LLM 呼叫 | headless `claude -p`(Claude Code 訂閱內),不走 Anthropic API | 零邊際成本;與 vault ingest.sh 同模式。翻盤條件:若 JSON 可靠度或 rate limit 成為實測瓶頸,改走 API(structured outputs) |
| D6 | v1 範圍 | Phase 1(M1 字幕路徑、M2 規則法、M3、M5、M6、M8)+ quick 模式 + vault 輸出 | 先端對端跑通、用真影片驗證留存率,再決定 M7 怎麼調 |
| D7 | 終止與移除 | 終止 = Ctrl+C(前景 CLI);vault 匯出為最後一步且原子寫入;`remove` 子指令半自動化事後移除 | 中斷絕不污染 vault;反悔成本壓到一行指令 |
| D8 | 簡→繁確定性轉換 | 加 `opencc`(s2twp),在 cli 對正文、在 vault 對標題/表頭跑查表轉換;vault 表頭不再自印標題(避免與正文標題重複) | 真實測試發現字幕為簡體時 full 模式整篇簡體、quick 僥倖轉繁——靠 LLM 保證繁體是非確定性的。opencc 查表 100% 穩定,prompt 的繁體指示退為雙保險。放寬「只用 yt-dlp+pyyaml」依賴限制,已獲 user 同意 |

**v1 不做**(依 spec Phase 2–4):M7 驗證回合、LLM 標點修復、Whisper fallback、
M4 畫格擷取、Type C 視覺輸入、M6b 系列 synthesis、自動分類 type、失敗續跑。

**語言支援(實測記錄,2026-07-07)**:字幕語言優先序 `[zh-TW, zh-Hant, zh, en]`。
- 中文影片:字幕常為簡體,經 opencc(D8)輸出繁體 zh-TW。
- 英文影片:`en` 會被選中,輸出仍是繁體中文摘要(英文專有名詞保留;opencc 對英文 no-op)。小限制:M2 斷句的句末標點集不含半形 `.`,英文只靠停頓/長度斷句,邊界較粗。
- 日文影片:`ja` 不在優先序,純日文字幕會在 M1 `FetchError` 中止(乾淨失敗,不產爛物)。**這也是 opencc 的安全前提——日文進不到轉換層;若未來加 `ja` 支援,opencc 必須加來源語言防護(s2twp 會誤轉部分日文漢字)。**

**選軌修正(實測記錄,2026-07-15)**:上面的字面優先序有個坑——英文影片的
`automatic_captions` 含 YouTube 自動翻譯的 `zh-Hant` 軌,會被優先序在 `en` 之前選中;
但翻譯字幕端點(`timedtext?...&tlang=`)被 YouTube 狠狠限流,實測原生 `en` 軌連打 6 發
全過、`zh-Hant` 翻譯軌幾乎全 `HTTP 429`。修正:`pick_subtitle_lang` 改為「人工字幕 >
影片原生語言(`meta['language']`)自動軌 > 翻譯自動軌(priority 序,最後手段)」——
這正好讓實作符合上一條「英文影片 en 會被選中」的原意,且交給 LLM 翻譯品質優於機翻。
殘留 429(某些片只有翻譯軌)由 `download_subtitle` 的 429 退避重試兜底(yt-dlp 自身
`--retries` 不覆蓋字幕下載)。前置條件:需裝 `curl_cffi`,否則字幕端點因缺 impersonation
一律 429(見 pyproject / LESSONS 2026-07-15)。

---

## 2. 架構

CLI 有兩個子指令:`yts <URL> [--type A|B|C] [...]`(主流程,下圖;`--type` 預設 A)與
`yts remove <url|video_id>`(事後移除,見 §6.1)。指令名 `yt-summary` 為等價舊名。

```
yts <URL> [--type A|B|C(預設 A)] [--mode auto|full|quick] [--no-vault]
   │
   ▼
 M1 擷取 ── yt-dlp:metadata + 字幕(人工>自動;zh-TW>zh-Hant>zh>en;json3)
   │         影片不存在/會員限定/無任何字幕 → 中止並回報
   ▼
 M2 前處理 ── 滾動字幕去重、規則法斷句(gap>0.8s)→ transcript.json
   │
   ├── duration < 600s 且 mode=auto ──▶ QUICK:全逐字稿 + type 特化 super prompt
   │                                     → 單次 claude -p(opus)→ article_final.md
   ▼
 FULL:M3 切分(章節優先 > token 窗 + overlap,對齊句尾)
   → M5 分段筆記(claude -p sonnet,並發 2,JSON 輸出)
   → M6 整合(claude -p opus)→ article_final.md
   │
   ▼
 M8 輸出 ── output/{video_id}/ 中間產物全落地 + run.log(各步耗時、usage)
   │
   ▼
 vault 輸出(預設開,--no-vault 關)── article_final.md → vault/raw/
```

M1/M2/M8/vault 輸出為兩條路徑共用;quick 與 full 只差中間段。

## 3. 檔案佈局

```
yt-summary/
├── pyproject.toml          # uv 管理;依賴:yt-dlp、pyyaml
├── config.yaml             # spec §9 + 本文件 §7 的擴充
├── src/yt_summary/
│   ├── cli.py              # 進入點:子指令(主流程/remove)、mode 判斷、pipeline 編排
│   ├── m1_fetch.py         # yt-dlp subprocess:metadata + 字幕下載
│   ├── m2_clean.py         # 去重、斷句 → transcript.json
│   ├── m3_segment.py       # 章節/token 窗切分 → segments.json
│   ├── m5_notes.py         # map:分段筆記(並發)→ segment_notes/*.json
│   ├── m6_reduce.py        # reduce:筆記 → article_final.md
│   ├── quick.py            # 短片單次呼叫路徑
│   ├── m8_output.py        # 產物落地、run.log 彙總
│   ├── vault.py            # 匯出 vault/raw/(原子寫入)+ remove 邏輯
│   ├── llm.py              # claude -p wrapper(subprocess、JSON 修復重試、usage 記錄)
│   ├── prompts.py          # 全部 prompt 模板,type 特化集中管理
│   └── tokens.py           # 啟發式 token 估算
└── tests/                  # pytest -q
```

## 4. LLM 層(llm.py)

- 介面:`call_llm(prompt: str, model: str, expect_json: bool = False) -> LLMResult`
  (`LLMResult` 含 `text`、`parsed`(若 expect_json)、`usage`、`duration`)。
- 實作:`claude -p --output-format json --model {haiku|sonnet|opus} --tools ""`,
  prompt 走 **stdin**(避免 argv 長度與 shell 逃逸問題)。用 `--tools ""` 讓工具完全
  不存在(比 `--allowedTools ""` 只擋放行更強)——這是純文字轉換任務;
  2026-07-07 已實測此組合可正常回傳。
- JSON 可靠度:prompt 內給明確 schema 與範例;解析失敗 → 一次「修復重試」
  (把壞輸出丟回去要求修成合法 JSON);再失敗 → 拋出標記,由呼叫端決定
  (M5:該段標記 `failed`,M6 收到缺段警告仍繼續;quick:整支中止回報)。
- 重試:subprocess 非零退出 → 重試 1 次(間隔 30s);再失敗同上。
- usage:從 CLI JSON 回傳取 tokens/cost 欄位寫入 run.log。
- 並發:M5 用 `ThreadPoolExecutor(max_workers=config.concurrency)`,預設 **2**
  ——claude -p 吃訂閱額度,並發過高會撞訂閱 rate limit。

## 5. 模組級規格差異(相對原 spec)

- **M2**:v1 只做規則法斷句(gap > 0.8s),LLM 標點修復留 Phase 2。
- **M5 模型檔位**:sonnet(spec 建議「中階」);**M6 / quick**:opus(文章品質關鍵)。
- **quick super prompt 要素**:角色(逐字稿分析員+文章作者一體)、完整逐字稿(帶時間戳)、
  metadata、type 特化規則(同 M5 的 B/C 條款)、輸出格式 = 與 M6 相同的文章結構
  (TL;DR **3–6 條**——短片內容量較小,刻意低於 M6 的 5–8 → 主題重組正文,
  每個主要論點附 `[mm:ss]` → 附錄依 type)、
  明確禁止省略次要論點。輸出直接是 markdown 文章(非 JSON)。
- **token 估算(tokens.py)**:`CJK 字元數 × 1.0 + 非 CJK 詞數 × 1.3`,
  spec 允許 ±10% 誤差;不引入 tokenizer 依賴。

## 6. vault 匯出(vault.py)

- 目標目錄:`/mnt/c/Users/micro/Documents/vault/raw/`(config 可改)。
- 檔名:`yt-{YYYYMMDD}-{標題 slug}-{video_id}.md`(video_id 保證唯一;重跑同影片
  覆蓋自己先前那份——「raw 只進不改」是對 vault 整理助手的規則,不約束產生器更新自己的產物)。
- 檔頭 metadata 區塊(嵌在文章 markdown 開頭):來源 URL、頻道、影片時長、type、
  產生日期——nightly ingest 依此填筆記的 `source` 欄位並判斷是否已攝入。
- **原子寫入**:先寫入同目錄暫存檔(`.tmp-` 前綴)再 `os.replace()` 到最終檔名。
  即使匯出瞬間撞上凌晨 ingest 掃描,ingest 也只會看到完整檔或沒有檔。
- 失敗處理:vault 目錄不可寫(如 Windows 磁碟未掛載)→ 警告並跳過,不影響 pipeline 主產物。

### 6.1 終止與移除

**執行中終止**:Ctrl+C(SIGINT 打到整個 process group,yt-dlp / claude -p 子行程
一併終止)。設計保證:vault 匯出是 pipeline 最後一步——中斷只會在 `output/{video_id}/`
留下中間產物(保留供 debug,重跑覆蓋),vault 不會有任何殘留。

**事後移除 `yts remove <url|video_id>`**:

1. 刪 `output/{video_id}/`。
2. 刪 `vault/raw/yt-*-{video_id}.md`(檔名含 video_id 即為此設計)。
3. grep `vault/wiki/` 各筆記的 `source:` 欄位比對影片 URL,偵測是否已被 nightly
   ingest 蒸餾:
   - 未攝入(ingest 前的反悔窗,最長約 24h)→ 回報「已完全移除」。
   - 已攝入 → **只列出受影響的筆記清單**,不動 wiki——wiki 的移除屬 vault 治理
     (其 CLAUDE.md §6:預設標 deprecated、物理刪除需明確指示並修復斷鏈),
     由使用者在 vault 的 claude session 處理;若該晚 ingest 只含此篇,
     也可直接 `git revert` 該筆自動 ingest commit。

## 7. config.yaml 擴充(相對 spec §9)

```yaml
defaults:
  language_out: zh-TW
  concurrency: 2            # claude -p 訂閱額度考量,調降自 spec 的 4
  output_dir: ./output

modes:
  quick_threshold_sec: 600  # < 10min 自動走 quick

llm:
  backend: claude-cli       # v1 唯一實作;保留欄位供未來 API backend
  models: { m5: sonnet, m6: opus, quick: opus }

vault:
  export: true
  raw_dir: /mnt/c/Users/micro/Documents/vault/raw
# types: A/B/C 段落照 spec §9,惟 frames 相關欄位 v1 不讀取
```

## 8. 錯誤處理(v1)

| 情況 | 處理 |
|------|------|
| 影片不存在 / 地區限制 / 會員限定 | 中止,回報 yt-dlp 錯誤原文 |
| 無任何字幕 | 中止,提示「Whisper fallback 為 Phase 2」 |
| 章節名無意義(Part 1/2/3 等) | 視同無章節,走 token 窗 |
| claude -p 非零退出 / JSON 修不回來 | M5:該段標 failed 繼續;quick:中止 |
| vault 目錄不可寫 | 警告並跳過匯出 |

## 9. 測試與驗收

- 單元測試(`pytest -q`,不需網路):M2 滾動字幕去重、M2 斷句、M3 章節/token 窗切分
  邊界(句尾對齊、小章節合併、overlap)、tokens.py 估算、vault 檔名 slug、
  vault 原子寫入與 remove(tmp 目錄模擬 raw/wiki:未攝入完全移除、已攝入列清單)、
  llm.py 的 JSON 修復流程(mock subprocess)。
- 煙霧測試(需網路 + claude 訂閱,手動跑):一支 <10min 影片走 quick、
  一支 30–40min Type A/B 影片走 full,端對端產出 article_final.md 並落 vault/raw。
- 驗收標準:沿用 spec §11 的留存率測試(golden list 命中 ≥ 85%)——由使用者
  以熟悉的影片人工驗證;數字保真(Type B)抽查。
