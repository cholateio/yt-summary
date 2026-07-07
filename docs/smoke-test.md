# 煙霧測試(手動,每次大改後跑)

需要:網路、已登入的 claude CLI(會消耗訂閱額度)。

1. **quick 路徑**:挑一支 < 15 分鐘、有字幕的影片
   `uv run yt-summary "<URL>" --type A`
   驗收:exit 0;`output/{id}/` 有 transcript.json、article_final.md、run.log
   (無 segments.json / segment_notes/);vault/raw 出現 `yt-*.md` 且檔頭含
   來源 URL;文章有 TL;DR 與 [mm:ss] 時間戳。
2. **full 路徑**:挑一支 30–40 分鐘 Type A/B 影片
   `uv run yt-summary "<URL>" --type B`
   驗收:segments.json 與 segment_notes/ 齊全;run.log 各步驟有 tokens/cost;
   Type B 文章附錄含數字彙整表。
3. **remove**:`uv run yt-summary remove <上面用的 id>`
   驗收:output 與 vault/raw 檔案消失;尚未被 ingest 時回報「已完全移除」。
4. **留存率**(spec §11):對一支你完整看過的影片列 15–20 條 golden list,
   對照文章命中 ≥ 85%;Type B 數字類 100% 原樣。
