from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from . import heuristic, llm as llm_mod
from .parser import Episode, fmt
from .rank import rank
from .validate import validate


def run(eps: list[Episode], cfg: dict, out_dir: Path, mode: str = "llm", log=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_num = {e.number: e for e in eps}
    t0 = time.time()
    pc = cfg.get("promo", {})
    ending = cfg.get("episode_ending", {})
    ep_dur = {e.number: e.duration for e in eps}
    min_len, max_len = pc.get("min_len", 20), pc.get("max_len", 60)

    candidates = []
    client = None
    if mode in ("llm", "both"):
        client = llm_mod.LLM(cfg["llm"], log_dir=out_dir / "llm_logs")
        win = cfg.get("window", 1)
        for i in range(len(eps)):
            window = eps[i:i + win]
            if win > 1 and len(window) < win and i > 0:
                break
            log(f"LLM proposing: episodes {[e.number for e in window]}")
            try:
                candidates += llm_mod.propose(client, window, n=pc.get("per_window", 5), ending=ending)
            except Exception as e:
                log(f"  failed: {e}")
    if mode in ("heuristic", "both"):
        for ep in eps:
            candidates += heuristic.propose(ep, min_len, max_len,
                                            resolution_from=ending.get("resolution_from_episode", 10**9))

    accepted, rejected = [], []
    for i, p in enumerate(candidates):
        p.id = f"P{i:03d}"
        ok, reasons = validate(p, by_num, min_len, max_len)
        p.warnings = reasons if ok else []
        (accepted if ok else rejected).append((p, reasons))
    accepted = [p for p, _ in accepted]
    log(f"{len(candidates)} candidates -> {len(accepted)} valid, {len(rejected)} rejected")

    weights = cfg.get("weights", {})
    top, rest = rank(accepted, len(eps), weights, top_k=pc.get("top_k", 10),
                     max_per_episode=pc.get("max_per_episode", 2),
                     ep_dur=ep_dur, ending=ending)

    # Second opinion from a "cold viewer" that sees only the clip.
    if client and cfg.get("cold_viewer", True):
        pool = top + rest[: pc.get("top_k", 10)]
        for p in pool:
            try:
                p.cold_view = llm_mod.cold_view(client, p, by_num)
            except Exception as e:
                p.cold_view = {"error": str(e)}
        top, rest = rank(top + rest, len(eps), weights, top_k=pc.get("top_k", 10),
                         max_per_episode=pc.get("max_per_episode", 2),
                     ep_dur=ep_dur, ending=ending)

    write_outputs(out_dir, top, rest, rejected, by_num)
    meta = {"mode": mode, "model": cfg.get("llm", {}).get("model") if client else None,
            "episodes": [e.number for e in eps], "candidates": len(candidates),
            "valid": len(accepted), "rejected": len(rejected),
            "llm_calls": client.calls if client else 0,
            "seconds": round(time.time() - t0, 1)}
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))
    log(json.dumps(meta))
    return {"top": top, "rest": rest, "rejected": rejected, "meta": meta}


def write_outputs(out_dir: Path, top, rest, rejected, by_num):
    (out_dir / "promos_ranked.json").write_text(
        json.dumps([p.to_dict() for p in top], indent=2, ensure_ascii=False))
    (out_dir / "promos_other_valid.json").write_text(
        json.dumps([p.to_dict() for p in rest], indent=2, ensure_ascii=False))
    (out_dir / "rejected.json").write_text(json.dumps(
        [{**p.to_dict(), "reject_reasons": r} for p, r in rejected], indent=2, ensure_ascii=False))

    with open(out_dir / "promos_ranked.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "id", "score", "duration_s", "segments", "hook",
                    "cliffhanger", "why", "source", "warnings", "cold_viewer"])
        for r, p in enumerate(top + rest, 1):
            w.writerow([r if p in top else "", p.id, p.final_score, p.duration,
                        segs_str(p), p.hook, p.cliffhanger, p.why, p.source,
                        "; ".join(p.warnings), p.cold_view.get("who_and_what", "") if p.cold_view else ""])

    lines = ["# Ranked promos\n"]
    for r, p in enumerate(top, 1):
        lines += [f"## {r}. {p.id}  score {p.final_score}  ({p.duration}s, {p.source})",
                  f"- **Segments:** {segs_str(p)}",
                  f"- **Hook:** {p.hook}", f"- **Cliffhanger:** {p.cliffhanger}",
                  f"- **Why:** {p.why}"]
        if p.warnings:
            lines.append(f"- **Warnings:** {'; '.join(p.warnings)}")
        if p.cold_view and "who_and_what" in p.cold_view:
            lines.append(f"- **Cold viewer:** {p.cold_view['who_and_what']}"
                         + (f" | confused by: {p.cold_view['confused_by']}" if p.cold_view.get("confused_by") else ""))
        lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def segs_str(p) -> str:
    return " + ".join(f"Ep{s.episode} {fmt(s.start)}-{fmt(s.end)}" for s in p.segments)
