"""Offline test of the LLM path with a fake model, so the plumbing can be
checked without an API key. Run: python -m tests.test_pipeline"""
import json
from pathlib import Path

import promo.llm as llm_mod
from promo.parser import load_dir
from promo.pipeline import run
from promo.validate import validate
from promo.model import Promo, Segment

FAKE_PROPOSALS = {"promos": [
    {   # good: stitched punch + proposal
        "segments": [{"episode": 3, "start_id": "E3-69", "end_id": "E3-73"},
                     {"episode": 3, "start_id": "E3-97", "end_id": "E3-117"}],
        "hook": "Stranger knocks a guard flat", "cliffhanger": "He kneels with a ring: 'accept my hand'",
        "why": "violence then a shock proposal, cut before her answer",
        "scores": {"hook": 5, "cliffhanger": 5, "standalone": 4, "spoiler_risk": 1}},
    {   # hallucinated id
        "segments": [{"episode": 3, "start_id": "E3-12", "end_id": "E3-999"}],
        "hook": "x", "cliffhanger": "y", "why": "z", "scores": {"hook": 5}},
    {   # too long
        "segments": [{"episode": 3, "start_id": "E3-0", "end_id": "E3-117"}],
        "hook": "x", "cliffhanger": "y", "why": "z", "scores": {"hook": 5}},
]}
FAKE_COLD = {"who_and_what": "A stranger rescues a jilted bride and proposes.",
             "confused_by": "", "standalone": 4, "would_stop_scrolling": 5, "want_to_see_next": 5}


class FakeLLM:
    def __init__(self, cfg, log_dir=None):
        self.calls = 0
        self.model = "fake"

    def json(self, system, user, tag):
        self.calls += 1
        return FAKE_PROPOSALS if tag.startswith("propose") else FAKE_COLD


def main():
    eps = [e for e in load_dir("data") if e.number == 3]
    by_num = {e.number: e for e in eps}

    # dialogue-straddle fix: shot E3-85 ends 01:43.00 but the line under it runs to 01:43.80
    p = Promo([Segment(3, "E3-66", "E3-85")])
    ok, _ = validate(p, by_num)
    assert ok and p.segments[0].end >= 103.8, p.segments[0]

    llm_mod.LLM = FakeLLM
    import promo.pipeline as pl
    pl.llm_mod.LLM = FakeLLM
    cfg = {"llm": {"model": "fake", "base_url": "x"}, "window": 1, "cold_viewer": True, "promo": {}}
    res = run(eps, cfg, Path("outputs/_test_fake_llm"), mode="llm", log=lambda *a: None)

    assert len(res["top"]) == 1, res["top"]
    top = res["top"][0]
    assert 20 <= top.duration <= 60 and len(top.segments) == 2
    reasons = [r[0] for _, r in res["rejected"]]
    assert any("invented" in r for r in reasons) and any("too long" in r for r in reasons), reasons
    print("OK", json.dumps(top.to_dict()["segments"]), top.duration, reasons)


if __name__ == "__main__":
    main()
