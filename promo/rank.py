"""Ranking = transparent weighted score + de-duplication + diversity.
Weights live in config.yaml so they can be argued about and changed."""
from __future__ import annotations

from .model import Promo

DEFAULT_WEIGHTS = {"hook": 0.35, "cliffhanger": 0.35, "standalone": 0.2,
                   "early_episode": 0.1, "spoiler_penalty": 0.15}


def _avg(*xs):
    xs = [float(x) for x in xs if x not in (None, "")]
    return sum(xs) / len(xs) if xs else 0.0


def ends_in_tail(p: Promo, ep_dur: dict, ending: dict) -> bool:
    """True if the promo's last segment ends in the final tail of an episode
    that is NOT in the finale stretch (so that ending is a planned cliffhanger)."""
    last = p.segments[-1]
    tail = ending.get("tail_seconds", 25)
    if last.episode >= ending.get("resolution_from_episode", 10**9):
        return False
    return last.end >= ep_dur.get(last.episode, 1e9) - tail - 0.01


def score(p: Promo, n_episodes: int, w: dict, ep_dur: dict | None = None,
          ending: dict | None = None) -> float:
    s, cv = p.scores, p.cold_view or {}
    hook = _avg(s.get("hook"), cv.get("would_stop_scrolling"))
    cliff = _avg(s.get("cliffhanger"), cv.get("want_to_see_next"))
    alone = _avg(s.get("standalone"), cv.get("standalone"))
    first_ep = min(p.episodes)
    # earlier episodes: fewer spoilers, and the viewer lands near episode 1
    early = 5.0 * (1 - (first_ep - 1) / max(n_episodes, 1))
    spoiler = float(s.get("spoiler_risk", 0) or 0)
    total = (w["hook"] * hook + w["cliffhanger"] * cliff + w["standalone"] * alone
             + w["early_episode"] * early - w["spoiler_penalty"] * spoiler)
    if ep_dur and ending and ends_in_tail(p, ep_dur, ending):
        total += float(ending.get("tail_bonus", 0.4)) * 5.0 / 5.0
    if any("visuals only" in x for x in p.warnings):
        total -= 0.2
    return round(total, 3)


def overlap(a: Promo, b: Promo) -> float:
    inter = union = 0.0
    for sa in a.segments:
        for sb in b.segments:
            if sa.episode == sb.episode:
                inter += max(0.0, min(sa.end, sb.end) - max(sa.start, sb.start))
    union = a.duration + b.duration - inter
    return inter / union if union > 0 else 0.0


def rank(promos: list[Promo], n_episodes: int, weights: dict | None = None,
         max_overlap: float = 0.4, max_per_episode: int = 2, top_k: int = 10,
         ep_dur: dict | None = None, ending: dict | None = None):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    for p in promos:
        p.final_score = score(p, n_episodes, w, ep_dur, ending)
    promos = sorted(promos, key=lambda p: -p.final_score)

    kept: list[Promo] = []
    for p in promos:                       # drop near-duplicates
        if all(overlap(p, k) <= max_overlap for k in kept):
            kept.append(p)

    top, per_ep, rest = [], {}, []         # diversity cap for the "post first" list
    for p in kept:
        e = min(p.episodes)
        if len(top) < top_k and per_ep.get(e, 0) < max_per_episode:
            top.append(p); per_ep[e] = per_ep.get(e, 0) + 1
        else:
            rest.append(p)
    return top, rest
