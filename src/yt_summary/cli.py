"""CLI 進入點:run(隱含)與 remove 兩個子指令。"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import m1_fetch, m2_clean, m3_segment, m5_notes, m6_reduce, quick, vault
from .config import load_config
from .llm import LLMError
from .m8_output import RunLog, write_outputs


def decide_mode(duration_sec: int, mode_arg: str, threshold: int) -> str:
    if mode_arg in ("full", "quick"):
        return mode_arg
    return "quick" if duration_sec < threshold else "full"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yt-summary")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="影片 → 重點文章")
    run.add_argument("url")
    run.add_argument("--type", required=True, choices=["A", "B", "C"], dest="type_code")
    run.add_argument("--mode", default="auto", choices=["auto", "full", "quick"])
    run.add_argument("--no-vault", action="store_true")
    run.add_argument("--config", default="config.yaml")
    run.set_defaults(func=cmd_run)

    rm = sub.add_parser("remove", help="移除已產生的摘要(output + vault/raw)")
    rm.add_argument("target", help="影片 URL 或 11 碼 video id")
    rm.add_argument("--config", default="config.yaml")
    rm.set_defaults(func=cmd_remove)
    return parser


def cmd_run(args) -> int:
    cfg = load_config(Path(args.config))
    runlog = RunLog()

    t = time.monotonic()
    meta = m1_fetch.fetch_meta(args.url)
    picked = m1_fetch.pick_subtitle_lang(meta)
    if picked is None:
        raise m1_fetch.FetchError("無任何字幕(手動/自動皆無)——Whisper fallback 為 Phase 2")
    lang, source = picked
    outdir = cfg.output_dir / meta["id"]
    outdir.mkdir(parents=True, exist_ok=True)
    sub_path = m1_fetch.download_subtitle(args.url, lang, source, outdir)
    runlog.add("M1 擷取", time.monotonic() - t)

    t = time.monotonic()
    cues = m2_clean.dedup_cues(m2_clean.parse_json3(sub_path))
    sentences = m2_clean.split_sentences(cues)
    transcript = m2_clean.build_transcript(meta, sentences, source, lang)
    runlog.add("M2 前處理", time.monotonic() - t)

    mode = decide_mode(transcript["duration_sec"], args.mode, cfg.quick_threshold_sec)
    segments = notes = None
    if mode == "quick":
        t = time.monotonic()
        article, calls = quick.quick_summarize(
            transcript, args.type_code, cfg.llm_models["quick"])
        runlog.add_llm("QUICK 單次呼叫", time.monotonic() - t, calls)
    else:
        tcfg = cfg.types[args.type_code]
        t = time.monotonic()
        segments = m3_segment.segment(transcript, tcfg.segment_tokens, tcfg.overlap_sec)
        runlog.add("M3 切分", time.monotonic() - t, note=f"{len(segments)} 段")

        t = time.monotonic()
        notes, m5_calls = m5_notes.map_segments(
            segments, transcript, args.type_code, cfg.llm_models["m5"], cfg.concurrency)
        n_failed = sum(1 for n in notes if n.get("status") != "ok")
        runlog.add_llm("M5 分段筆記", time.monotonic() - t, m5_calls,
                       note=f"{n_failed} failed" if n_failed else "")

        t = time.monotonic()
        article, m6_calls = m6_reduce.reduce_notes(
            notes, transcript, args.type_code, cfg.llm_models["m6"])
        runlog.add_llm("M6 整合", time.monotonic() - t, m6_calls)

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
