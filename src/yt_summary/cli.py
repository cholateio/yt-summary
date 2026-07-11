"""CLI 進入點:run(隱含)與 remove 兩個子指令。"""
from __future__ import annotations

import argparse
import functools
import sys
import time
from pathlib import Path

from . import convert, m1_fetch, m2_clean, m3_segment, m5_notes, m6_reduce, quick, vault
from .config import load_config
from .llm import LLMError, call_llm
from .m8_output import RunLog, write_outputs
from .progress import Reporter
from .prompts import ts


def decide_mode(duration_sec: int, mode_arg: str, threshold: int) -> str:
    if mode_arg in ("full", "quick"):
        return mode_arg
    return "quick" if duration_sec < threshold else "full"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()  # prog 由 argv[0] 決定(yts / yt-summary 皆可)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="影片 → 重點文章")
    run.add_argument("url")
    run.add_argument("--type", default="A", choices=["A", "B", "C"], dest="type_code",
                     help="A=AI/談話(預設) B=財經 C=coding")
    run.add_argument("--mode", default="auto", choices=["auto", "full", "quick"])
    run.add_argument("--no-vault", action="store_true")
    run.add_argument("--quiet", action="store_true", help="關閉進度輸出(stderr)")
    run.add_argument("--config", default="config.yaml")
    run.set_defaults(func=cmd_run)

    rm = sub.add_parser("remove", help="移除已產生的摘要(output + vault/raw)")
    rm.add_argument("target", help="影片 URL 或 11 碼 video id")
    rm.add_argument("--config", default="config.yaml")
    rm.set_defaults(func=cmd_remove)
    return parser


def cmd_run(args, reporter: Reporter | None = None) -> int:
    cfg = load_config(Path(args.config))
    runlog = RunLog()
    rep = reporter or Reporter(enabled=not args.quiet)

    # 重試原本是靜默 sleep 30s,無從分辨卡死或重試——綁進所有下游 LLM 呼叫。
    def on_retry(attempt, retries, wait_sec, err):
        rep.warn(f"claude -p 失敗,{wait_sec}s 後重試({attempt}/{retries}):{str(err)[:120]}")

    call = functools.partial(call_llm, on_retry=on_retry)

    try:
        rep.begin("抓取影片資訊")
        t = time.monotonic()
        meta = m1_fetch.fetch_meta(args.url)
        picked = m1_fetch.pick_subtitle_lang(meta)
        if picked is None:
            raise m1_fetch.FetchError("無任何字幕(手動/自動皆無)——Whisper fallback 為 Phase 2")
        lang, source = picked
        duration = int(meta.get("duration") or 0)  # 與 transcript["duration_sec"] 同源
        mode = decide_mode(duration, args.mode, cfg.quick_threshold_sec)
        rep.set_total(4 if mode == "full" else 3)
        rep.ok(f"「{meta.get('title', '')}」({ts(duration)}) → 模式 {mode}")

        rep.step(f"下載字幕({lang},{'手動' if source == 'manual_subs' else '自動'})")
        outdir = cfg.output_dir / meta["id"]
        outdir.mkdir(parents=True, exist_ok=True)
        sub_path = m1_fetch.download_subtitle(args.url, lang, source, outdir)
        runlog.add("M1 擷取", time.monotonic() - t)
        rep.ok()

        rep.step("前處理")
        t = time.monotonic()
        cues = m2_clean.dedup_cues(m2_clean.parse_json3(sub_path))
        sentences = m2_clean.split_sentences(cues)
        transcript = m2_clean.build_transcript(meta, sentences, source, lang)
        runlog.add("M2 前處理", time.monotonic() - t)
        rep.ok(f"{len(sentences)} 句")

        segments = notes = None
        if mode == "quick":
            rep.step(f"產生文章(quick 單次呼叫,{cfg.llm_models['quick']})")
            t = time.monotonic()
            article, calls = quick.quick_summarize(
                transcript, args.type_code, cfg.llm_models["quick"], call=call)
            runlog.add_llm("QUICK 單次呼叫", time.monotonic() - t, calls)
            rep.ok()
        else:
            tcfg = cfg.types[args.type_code]
            t = time.monotonic()
            segments = m3_segment.segment(transcript, tcfg.segment_tokens, tcfg.overlap_sec)
            runlog.add("M3 切分", time.monotonic() - t, note=f"{len(segments)} 段")

            rep.step(f"分段筆記 {len(segments)} 段"
                     f"({cfg.llm_models['m5']},並發 {cfg.concurrency})")
            t = time.monotonic()

            def on_segment(done, total, seg_id, error):
                if error:
                    rep.warn(f"第 {seg_id} 段失敗,該段內容將缺漏:{error[:120]}")
                rep.progress(done, total)

            notes, m5_calls = m5_notes.map_segments(
                segments, transcript, args.type_code, cfg.llm_models["m5"],
                cfg.concurrency, call=call, on_progress=on_segment)
            n_failed = sum(1 for n in notes if n.get("status") != "ok")
            runlog.add_llm("M5 分段筆記", time.monotonic() - t, m5_calls,
                           note=f"{n_failed} failed" if n_failed else "")
            rep.ok(f"{len(segments) - n_failed}/{len(segments)} 段成功"
                   + (f",{n_failed} 段失敗" if n_failed else ""))

            rep.step(f"整合成文({cfg.llm_models['m6']})")
            t = time.monotonic()
            article, m6_calls = m6_reduce.reduce_notes(
                notes, transcript, args.type_code, cfg.llm_models["m6"], call=call)
            runlog.add_llm("M6 整合", time.monotonic() - t, m6_calls)
            rep.ok()
    except BaseException:
        rep.close_line()  # 未收尾的步驟行斷掉,錯誤訊息才不會黏在後面
        raise

    t = time.monotonic()
    article = convert.to_traditional_markdown(article)  # 確定性簡→繁,但保留 code 區塊
    runlog.add("簡繁轉換", time.monotonic() - t)

    write_outputs(outdir, transcript=transcript, segments=segments,
                  notes=notes, article=article, runlog=runlog)

    if cfg.vault_export and not args.no_vault:
        try:
            p = vault.export_article(article, transcript, cfg.vault_raw_dir, args.type_code)
            print(f"已匯出 vault:{p}")
        except OSError as e:
            print(f"警告:vault 匯出失敗,已跳過({e})", file=sys.stderr)

    print(runlog.summary_line())
    print(f"完成(mode={mode}):{outdir / 'article_final.md'}")
    return 0


def cmd_remove(args) -> int:
    cfg = load_config(Path(args.config))
    wiki_dir = cfg.vault_raw_dir.parent / "wiki"
    report = vault.remove(args.target, cfg.output_dir, cfg.vault_raw_dir, wiki_dir)
    print(f"video_id:{report.video_id}")
    print(f"output/ 移除:{'是' if report.removed_output else '無此目錄'}")
    print(f"vault/raw 移除:{report.removed_raw or '無對應檔案'}")
    if report.affected_wiki:
        print("注意:以下 wiki 筆記的 source 指向此影片(已被 ingest),"
              "請在 vault 的 claude session 依其治理規則處理:")
        for f in report.affected_wiki:
            print(f"  - wiki/{f}")
    else:
        print("wiki 無引用——已完全移除。")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("run", "remove") and not argv[0].startswith("-"):
        argv = ["run"] + argv  # `yt-summary <URL> ...` 隱含 run
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (m1_fetch.FetchError, LLMError, ValueError) as e:
        print(f"錯誤:{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
