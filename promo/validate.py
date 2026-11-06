"""Code-side checks. The LLM only names event IDs; this module turns them into
real timestamps, snaps them to clean shot cuts, and rejects anything that
breaks the rules. Nothing the model says about time is trusted."""
from __future__ import annotations

import bisect

from .model import Promo
from .parser import Episode, shot_starts, shot_ends

MIN_LEN, MAX_LEN = 20.0, 60.0
HOOK_WINDOW = 3.0


def _snap_down(points, t):
    i = bisect.bisect_right(points, t + 1e-6) - 1
    return points[max(i, 0)]


def _snap_up(points, t):
    i = bisect.bisect_left(points, t - 1e-6)
    return points[min(i, len(points) - 1)]


def validate(promo: Promo, eps: dict[int, Episode],
             min_len=MIN_LEN, max_len=MAX_LEN) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    by_id = {e.id: e for ep in eps.values() for e in ep.events}

    for seg in promo.segments:
        if seg.episode not in eps:
            return False, [f"unknown episode {seg.episode}"]
        a, b = by_id.get(seg.start_id), by_id.get(seg.end_id)
        if a is None or b is None:
            return False, [f"unknown event id {seg.start_id if a is None else seg.end_id} (model invented it)"]
        if a.episode != seg.episode or b.episode != seg.episode:
            return False, [f"segment ids {seg.start_id}..{seg.end_id} not in episode {seg.episode}"]
        if b.end <= a.start:
            return False, [f"segment end {seg.end_id} is before start {seg.start_id}"]

        ep = eps[seg.episode]
        starts, ends = shot_starts(ep), shot_ends(ep)
        start, end = _snap_down(starts, a.start), _snap_up(ends, b.end)

        # Never cut through a line of dialogue: widen until stable.
        dialogue = [e for e in ep.events if e.kind == "DIALOGUE"]
        for _ in range(10):
            moved = False
            for d in dialogue:
                if d.start < start - 0.05 < d.end - 0.1:
                    start = _snap_down(starts, d.start); moved = True
                if d.start + 0.1 < end + 0.05 < d.end:
                    end = _snap_up(ends, d.end); moved = True
            if not moved:
                break
        seg.start, seg.end = round(start, 2), round(end, 2)

    # order + overlap across segments
    for x, y in zip(promo.segments, promo.segments[1:]):
        if (x.episode, x.start) > (y.episode, y.start):
            reasons.append("segments out of story order (allowed, but flagged)")
        if x.episode == y.episode and y.start < x.end:
            return False, ["segments overlap"]

    dur = promo.duration
    if dur < min_len:
        return False, [f"too short: {dur:.1f}s < {min_len:.0f}s"]
    if dur > max_len:
        return False, [f"too long: {dur:.1f}s > {max_len:.0f}s"]

    # hook window: is anything audible/visible-as-action in the first 3s?
    first = promo.segments[0]
    ep = eps[first.episode]
    opening = [e for e in ep.events
               if first.start - 0.01 <= e.start < first.start + HOOK_WINDOW and e.kind != "CAMERA"]
    if not opening:
        reasons.append("no line or action in first 3s - hook depends on visuals only")
    return True, reasons
