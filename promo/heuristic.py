"""Rule-based baseline. Runs with no API key, so the tool always produces
something, and gives a floor the LLM has to beat. The keyword lists are a
starting point - tune them per genre."""
from __future__ import annotations

import re

from .model import Promo, Segment
from .parser import Episode, fmt

SHOCK_WORDS = [
    "slap", "strike", "punch", "grab", "seize", "drag", "guards", "remove her",
    "kneel", "one knee", "ring", "gasp", "scream", "collapse", "tear",
    "cannot marry", "marrying me", "disowned", "not anymore", "take your hands",
    "let her go", "let me go", "never", "betray", "stole", "humiliat",
]
OPEN_LOOP_WORDS = [
    "accept my hand", "who are you", "why are you", "what happens", "leave where",
    "ring", "one knee", "fade", "cliffhanger", "anticipation", "frozen",
    "doors swing", "cut to black",
]
RESOLVED_WORDS = ["i accept", "husband and wife", "i am.", "i truly mean it", "let us proceed"]


def _txt(e) -> str:
    return (e.text + " " + " ".join(e.modifiers)).lower()


def hook_score(events) -> tuple[float, str]:
    best, line = 0.0, ""
    for e in events:
        if e.kind == "CAMERA":
            continue
        t = _txt(e)
        s = 1.0
        s += 1.5 * sum(w in t for w in SHOCK_WORDS)
        if e.kind == "DIALOGUE":
            if "!" in e.text:
                s += 0.75
            if len(e.text.split()) <= 7:
                s += 0.5          # short, punchy lines read in 3s
            if e.text.startswith("..."):
                s -= 1.5          # starts mid-sentence
        if e.kind == "SOUND FX":
            s += 0.5
        if s > best:
            best, line = s, (f'{e.speaker}: "{e.text}"' if e.kind == "DIALOGUE" else e.text)
    return min(best, 5.0), line


def cliff_score(events, is_episode_end: bool) -> tuple[float, str]:
    real = [e for e in events if e.kind != "CAMERA"]
    if not real:
        return 1.0, ""
    last = real[-1]
    t = _txt(last)
    s = 1.5
    if last.text.rstrip().endswith("?"):
        s += 1.5
    if last.text.rstrip().endswith("...") or last.text.rstrip().endswith("…"):
        s += 1.0
    s += 1.0 * sum(w in t for w in OPEN_LOOP_WORDS)
    if any(w in t for w in RESOLVED_WORDS):
        s -= 2.0
    if is_episode_end:
        s += 1.0                  # writers end episodes on cliffhangers
    line = f'{last.speaker}: "{last.text}"' if last.kind == "DIALOGUE" else last.text
    return max(1.0, min(s, 5.0)), line


def standalone_score(events) -> float:
    dlg = [e for e in events if e.kind == "DIALOGUE"]
    speakers = {e.speaker for e in dlg}
    s = 4.0
    if dlg and dlg[0].text.startswith("..."):
        s -= 1.5
    if len(speakers) > 4:
        s -= 1.0
    if len(dlg) < 3:
        s -= 1.0
    return max(1.0, s)


def propose(ep: Episode, min_len=20.0, max_len=60.0, per_episode=6,
            resolution_from=10**9) -> list[Promo]:
    cams = [e for e in ep.events if e.kind == "CAMERA"]
    shot_end_times = sorted({c.end for c in cams})
    out: list[Promo] = []
    for c in cams:
        s = c.start
        opening = [e for e in ep.events if s - 0.01 <= e.start < s + 3.0]
        h, hook_line = hook_score(opening)
        if h < 2.5:
            continue
        best = None
        for t_end in shot_end_times:
            if not (min_len <= t_end - s <= max_len):
                continue
            window = [e for e in ep.events if e.start >= s - 0.01 and e.end <= t_end + 0.01]
            tail = [e for e in window if e.end >= t_end - 4.0]
            cl, cliff_line = cliff_score(tail, is_episode_end=abs(t_end - ep.duration) < 0.05 and ep.number < resolution_from)
            st = standalone_score(window)
            score = 0.4 * h + 0.4 * cl + 0.2 * st
            if best is None or score > best[0]:
                last_evt = [e for e in window if e.end <= t_end + 0.01][-1]
                best = (score, t_end, cl, cliff_line, st, last_evt.id)
        if best is None:
            continue
        score, t_end, cl, cliff_line, st, end_id = best
        out.append(Promo(
            segments=[Segment(ep.number, c.id, end_id)],
            hook=hook_line, cliffhanger=cliff_line,
            why=f"rule-based: hook {h:.1f}, cliff {cl:.1f}, standalone {st:.1f}",
            scores={"hook": round(h, 2), "cliffhanger": round(cl, 2),
                    "standalone": round(st, 2), "spoiler_risk": 0},
            source="heuristic",
        ))
    out.sort(key=lambda p: -(0.4 * p.scores["hook"] + 0.4 * p.scores["cliffhanger"] + 0.2 * p.scores["standalone"]))
    return out[: per_episode * 3]   # ranker de-duplicates overlaps later
