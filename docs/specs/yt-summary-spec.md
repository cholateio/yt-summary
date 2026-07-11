# YouTube 影片轉重點文章 — 自動化 Pipeline 規格書

版本:v0.1(草稿)
目標讀者:實作者本人
更新日期:2026-07-06

---

## 1. 目標與非目標

### 1.1 目標

- 輸入一個 YouTube 網址(或一組系列影片網址),自動產出一篇「重點文章」,資訊留存率顯著高於現行「長 prompt + 網址一次性摘要」的做法。
- 對 15 分鐘以上的長影片,重點遺漏率要可被驗證、可被量測(見第 11 節驗收標準)。
- 針對三類影片提供不同參數配置:
  - **Type A**:AI 概念 / 工作流分享,談話為主,15–40 分鐘
  - **Type B**:財經 / 量化交易 / 市場調查,談話為主,30–60+ 分鐘,數字密集
  - **Type C**:coding challenge / 程式架構,30+ 分鐘,常為系列,畫面資訊密集

### 1.2 非目標(至少 v1 不做)

- 即時處理(直播中摘要)
- 影片剪輯或 highlight 影片產出
- 多語言翻譯(輸出語言固定為 zh-TW,原文專有名詞保留)

---

## 2. 影片分類與參數表

分類方式:v1 由使用者在執行時指定 `--type A|B|C`(2026-07-11 起未給則預設 A);v2 可改為由 metadata(標題、頻道、章節名)自動判斷。

| 參數 | Type A(AI 談話) | Type B(財經) | Type C(coding) |
|---|---|---|---|
| 切分優先序 | 章節 > token 窗 | 章節 > token 窗 | 章節 > token 窗 |
| 每段目標 token 數 | 3,000–4,000 | 3,000–4,000 | 2,000–3,000 |
| 對應時長(參考) | 8–12 min | 8–12 min | 5–8 min |
| 段落重疊(overlap) | 45 s | 45 s | 30 s |
| 畫格擷取 | 關閉 | 選配(有圖表時開) | **必開** |
| 分段筆記特別規則 | 保留論點推理鏈 | **數字/日期/代號原樣保留** | **程式碼完整重現** |
| 系列模式 | 否 | 否 | 是(跨影片 synthesis) |

---

## 3. 系統架構總覽

```
輸入(URL, type, 選項)
   │
   ▼
[M1 擷取] ── yt-dlp:metadata + 章節 + 字幕;無字幕 → 音軌 + Whisper
   │
   ▼
[M2 前處理] ── 字幕去重、斷句、標點修復,產出帶時間戳的乾淨逐字稿
   │
   ▼
[M3 切分] ── 章節優先,否則 token 窗切分 + overlap
   │
   ├──(Type C / 選配)──▶ [M4 畫格擷取] ── ffmpeg 場景偵測 → 去重 → 按時間戳掛到對應段落
   │                          │
   ▼◀─────────────────────────┘
[M5 分段筆記 map] ── 每段各自呼叫 LLM,產出結構化詳細筆記(JSON)
   │
   ▼
[M6 整合 reduce] ── 所有分段筆記 → 一篇文章(markdown)
   │
   ▼
[M7 驗證回合] ── 逐字稿 vs 文章比對 → 遺漏清單 → 補寫
   │
   ▼
[M8 輸出] ── 文章.md + 中間產物(可追溯)
```

每個模組的中間產物都落地成檔案(見第 5 節),方便單獨重跑某一步、debug,以及日後替換某模組的實作。

---

## 4. 模組規格

### M1 擷取

工具:`yt-dlp`

1. 取 metadata:`--dump-json`,需要的欄位:`title`、`duration`、`chapters`、`uploader`、`upload_date`、`webpage_url`。
2. 字幕優先序:**人工上傳字幕 > 自動字幕**;語言優先序:`zh-TW > zh-Hant > zh > en`。格式取 `json3` 或 `vtt`(json3 帶詞級時間戳,較好處理)。
3. 無任何字幕時 fallback:`-x --audio-format m4a` 抓音軌,交給 Whisper(建議 `faster-whisper`,`medium` 或 `large-v3` 模型;中英夾雜內容建議 large-v3),輸出帶 segment 時間戳的逐字稿。
4. 系列模式:輸入為 playlist URL 或多個 URL,對每支影片各自執行 M1–M7,最後多跑一次 M6b(見 §7)。

錯誤處理:影片不存在 / 地區限制 / 會員限定 → 直接中止並回報;字幕下載失敗但影片存在 → 自動走 Whisper fallback 並在 log 標註。

### M2 前處理

輸入:原始字幕檔;輸出:`transcript.json`(見 §5.1)。

必做:

1. **自動字幕去重**:YouTube 自動字幕是滾動式,相鄰 cue 會有大量重複文字,需合併去重(比對相鄰 cue 的重疊子字串)。
2. **斷句與標點修復**:自動字幕幾乎沒有標點。二選一:
   - 規則法:依停頓時間(gap > 0.8s)斷句 — 快但品質普通;
   - LLM 法:每 2,000 tokens 一批丟給便宜的小模型,指令「只加標點與分段,不得改動任何字」— 品質好,建議採用。批次處理時保留每句對應的原始時間範圍。
3. 保留時間戳:最終逐字稿以「句」為單位,每句帶 `start` / `end`(秒)。

### M3 切分

輸入:`transcript.json` + 章節資訊;輸出:`segments.json`。

演算法:

1. **有章節**:以章節為初始邊界。若某章節 token 數 > 上限(依 type,見 §2),在章節內再用 token 窗細切;若某章節 < 800 tokens,與相鄰章節合併。
2. **無章節**:純 token 窗切分,目標 token 數依 type;邊界必須對齊「句」的結尾(不可切在句中)。
3. **overlap**:每段開頭往前多帶 30–45 秒的內容,標記為 `context_prefix`(在 M5 的 prompt 中告知模型「此為前段脈絡,僅供理解,不需重複記錄」)。
4. token 計數:用目標 LLM 對應的 tokenizer 估算即可,誤差 ±10% 可接受。

### M4 畫格擷取(Type C 必開,Type B 選配)

工具:`ffmpeg` + perceptual hash 去重。

1. 場景偵測:`ffmpeg -i in.mp4 -vf "select='gt(scene,0.25)',showinfo" ...` 抽出場景變化畫格;另外加一條保底規則:任兩張畫格間隔不得超過 60 秒(避免長時間停留同一畫面但內容有滾動,例如捲動程式碼)。
2. 針對「同畫面捲動」問題:對程式教學影片,可將保底間隔縮到 20–30 秒,再靠去重刪掉真正相同的畫格。
3. 去重:perceptual hash(如 `imagehash.phash`),hamming distance < 8 視為重複,保留較晚的一張(程式碼通常越寫越完整)。
4. 每張畫格記錄時間戳,依 `segments.json` 的時間範圍掛到對應段落。
5. 上限控制:每段最多送 N 張(建議 6–10 張,依 API 成本調整);超過時優先保留與相鄰畫格差異最大的。

### M5 分段筆記(map)

對每個 segment 各自呼叫一次 LLM。**這一步的目標是「詳盡」而不是「精簡」**——寧可冗長,壓縮是 M6 的事。

Prompt 要素(所有 type 共用):

- 角色:逐字稿分析員,任務是不遺漏地記錄。
- 輸入:該段逐字稿(含時間戳)、`context_prefix`、影片 metadata(標題、章節名)、(Type C)該段畫格。
- 輸出格式:JSON(見 §5.2),包含:主題句、所有論點(每個論點附時間戳與一句原文依據)、提及的工具/專有名詞、數字與事實、程式碼、金句、講者明示的重點提示(「這個很重要」「記下來」)。
- 明確禁止:不得省略「看似次要」的論點;不確定的內容標 `confidence: low` 而不是丟棄。

Type 特化規則:

- **Type B**:所有數字、百分比、日期、股票/商品代號、指標名稱必須原樣抄錄,禁止改寫為「大約」「不錯」等模糊描述。
- **Type C**:畫格中的程式碼要完整轉錄(OCR 語意化),與講者口述對照;記錄「口述說要做 X,畫面實際寫的是 Y」的差異;檔案名稱、函式名、指令列參數原樣保留。

併發:各段互相獨立,可平行呼叫(注意 API rate limit,建議並發數 3–5、指數退避重試)。

### M6 整合(reduce)

輸入:全部 `segment_notes/*.json` + metadata;輸出:`article_draft.md`。

Prompt 要素:

- 任務:把分段筆記整合成一篇結構完整的文章,**以資訊留存為第一優先,可讀性第二**。
- 規則:
  1. 相鄰段落因 overlap 造成的重複論點需合併,但不同角度的重述要保留。
  2. 每個主要論點後附時間戳(格式 `[12:34]`),讓讀者可跳回原片。
  3. 文章結構:TL;DR(5–8 條)→ 依主題重組的正文(不必然照影片順序)→ 附錄(工具清單 / 數字彙整表 / 完整程式碼區塊,依 type)。
  4. Type B 附錄必含「數字彙整表」;Type C 附錄必含完整程式碼區塊(標明對應時間戳)。
- 若總筆記量超過單次呼叫的合理範圍(> ~60k tokens),先做一層「每 3–4 段合併」的中間 reduce 再做最終 reduce。

### M7 驗證回合

兩步:

1. **遺漏檢查**:輸入 = 完整逐字稿 + `article_draft.md`,要求模型輸出 JSON 清單:「出現在逐字稿、具有資訊價值、但未進入文章」的項目,每項附時間戳與重要性評分(1–3)。
2. **補寫**:重要性 ≥ 2 的項目連同草稿一起送回模型,要求把遺漏項目補進適當章節,輸出 `article_final.md`。

若逐字稿過長無法單次比對,以「每 3 個 segment 對整篇文章」分批檢查,遺漏清單合併後去重再補寫。

### M8 輸出

```
output/{video_id}/
├── article_final.md        # 最終文章
├── article_draft.md        # M6 草稿(留檔比對)
├── transcript.json         # M2 產物
├── segments.json           # M3 產物
├── segment_notes/          # M5 產物,每段一個 json
├── frames/                 # M4 產物(Type C)
├── omissions.json          # M7 遺漏清單
└── run.log                 # 各步驟耗時、token 用量、成本估算
```

---

## 5. 中間資料格式

### 5.1 transcript.json

```json
{
  "video_id": "abc123",
  "title": "...",
  "duration_sec": 2400,
  "source": "manual_subs | auto_subs | whisper",
  "language": "zh-TW",
  "chapters": [{"title": "...", "start": 0, "end": 300}],
  "sentences": [
    {"i": 0, "start": 0.0, "end": 4.2, "text": "..."}
  ]
}
```

### 5.2 segment_note(M5 輸出)

```json
{
  "segment_id": 3,
  "time_range": [612.0, 1180.5],
  "topic": "本段主題一句話",
  "points": [
    {
      "claim": "論點完整敘述",
      "timestamp": 645.2,
      "evidence_quote": "逐字稿原句(可截短)",
      "importance": 3,
      "confidence": "high"
    }
  ],
  "entities": ["工具名", "專有名詞"],
  "facts_numbers": [{"value": "年化 14.2%", "context": "...", "timestamp": 700.1}],
  "code_blocks": [{"lang": "python", "code": "...", "timestamp": 820.0, "note": "口述與畫面差異(若有)"}],
  "speaker_emphasis": ["講者明示重要的內容"]
}
```

---

## 6. LLM 呼叫規格

| 步驟 | 模型等級建議 | max_tokens | temperature | 備註 |
|---|---|---|---|---|
| M2 標點修復 | 小/便宜 | 與輸入等長 | 0 | 逐批,禁止改字 |
| M5 分段筆記 | 中階 | 4,000+ | 0–0.2 | JSON 輸出;Type C 需支援視覺輸入 |
| M6 整合 | 高階 | 8,000+ | 0.3 | 文章品質關鍵,用最好的模型 |
| M7 驗證 | 中–高階 | 4,000 | 0 | JSON 輸出 |

通用:

- 所有 JSON 輸出使用 structured output / JSON mode(若 API 支援),並在解析失敗時做一次「修復重試」(把壞掉的輸出丟回去要求修成合法 JSON)。
- 重試策略:網路/限流錯誤 → 指數退避,最多 3 次;內容性失敗(JSON 壞、輸出截斷)→ 換 seed 重打 1 次後標記人工檢查。
- 每次呼叫記錄 input/output tokens 到 `run.log`,結束時彙總成本。

---

## 7. 系列影片模式(Type C)

1. 每支影片獨立跑完 M1–M7,各自產出 `article_final.md`。
2. 追加 **M6b 跨影片 synthesis**:輸入 = 各集的 TL;DR + 各集 segment_notes 的 `topic` 與高重要性 points,輸出一篇「系列總覽」:整體架構演進、各集之間的依賴關係(第 3 集重構了第 1 集的哪個模組)、完整技術棧清單、建議閱讀/觀看順序。
3. 集與集之間的引用格式:`[EP2 15:30]`。

---

## 8. 邊界情況

| 情況 | 處理 |
|---|---|
| 無字幕且 Whisper 失敗 | 中止,回報 |
| 影片 > 2 小時 | 正常切分即可,但 M7 強制走分批比對 |
| 章節名稱無意義(如「Part 1/2/3」) | 視同無章節,走 token 窗 |
| 中英夾雜逐字稿 | Whisper 用 large-v3;M2 標點修復 prompt 註明保留英文原文 |
| 自動字幕品質極差(錯字率高) | M5 prompt 加註「字幕由 ASR 產生,遇到疑似錯字請依上下文合理推斷並標註」 |
| Type C 但影片無法下載視訊(僅音訊) | 降級為純文字流程,log 警告 |

---

## 9. 設定檔範例(config.yaml)

```yaml
defaults:
  language_out: zh-TW
  concurrency: 4
  output_dir: ./output

types:
  A:
    segment_tokens: [3000, 4000]
    overlap_sec: 45
    frames: false
  B:
    segment_tokens: [3000, 4000]
    overlap_sec: 45
    frames: optional        # CLI flag --frames 開啟
    extra_rules: [preserve_numbers]
  C:
    segment_tokens: [2000, 3000]
    overlap_sec: 30
    frames: true
    frames_per_segment_max: 8
    scene_threshold: 0.25
    frame_min_interval_sec: 25
    extra_rules: [preserve_code]
    series_mode: true
```

---

## 10. 實作階段建議

**Phase 1 — MVP(純文字,涵蓋 Type A/B)**
M1(僅字幕路徑)→ M2(規則法斷句即可)→ M3 → M5 → M6 → M8。
先不做 Whisper fallback、M4、M7。目標:端到端跑通,用 2–3 支你熟的影片人工驗證留存率。

**Phase 2 — 品質強化**
加 M7 驗證回合、M2 改 LLM 標點修復、Whisper fallback。

**Phase 3 — 視覺與系列(Type C)**
M4 畫格擷取 + M5 視覺輸入 + M6b 系列 synthesis。

**Phase 4 — 體驗**
自動分類 type、成本報表、失敗續跑(從中間產物 resume)。

---

## 11. 驗收標準

- **留存率測試**:挑一支你已完整看過的 40 分鐘影片,自己先列出 15–20 個「必須出現的重點」作為 golden list,pipeline 產出的文章命中 ≥ 85% 視為合格(現行做法可先量一次當 baseline)。
- **數字保真(Type B)**:golden list 中的數字類項目命中率 100%,且數值原樣未被模糊化。
- **程式碼保真(Type C)**:文章附錄中的程式碼可直接對照影片畫面,關鍵區塊無缺漏。
- **可追溯性**:文章中任一論點的時間戳,跳回影片後 ±30 秒內能找到對應內容。
- **成本與時間**:單支 40 分鐘影片,全流程 API 成本與耗時記錄於 run.log,作為後續優化基準(v1 不設硬上限,先量測)。
