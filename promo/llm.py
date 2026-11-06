"""Model access. Any OpenAI-compatible endpoint works (Gemini, Groq, OpenRouter,
Ollama, OpenAI, or the Kuku-provided API) - change config.yaml, not code."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .model import Promo, Segment
from .parser import Episode, fmt
from . import prompts


class LLM:
    def __init__(self, cfg: dict, log_dir: Path | None = None):
        from openai import OpenAI
        key = os.environ.get(cfg.get("api_key_env", ""), "") or cfg.get("api_key", "") or "none"
        self.client = OpenAI(base_url=cfg["base_url"], api_key=key)
        self.model = cfg["model"]
        self.temperature = cfg.get("temperature", 0.3)
        self.sleep = cfg.get("sleep_between_calls", 0)
        self.log_dir = log_dir
        self.calls = 0

    def json(self, system: str, user: str, tag: str) -> dict:
        last_err = None
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, temperature=self.temperature,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                )
                self.calls += 1
                text = resp.choices[0].message.content or ""
                self._log(tag, attempt, user, text)
                if self.sleep:
                    time.sleep(self.sleep)
                return extract_json(text)
            except Exception as e:      # network, rate limit, bad JSON
                last_err = e
                self._log(tag, attempt, user, f"ERROR: {e!r}")
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM failed for {tag}: {last_err}")

    def _log(self, tag, attempt, prompt, text):
        if not self.log_dir:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / f"{tag}_try{attempt}.txt").write_text(
            f"MODEL: {self.model}\n\n=== PROMPT ===\n{prompt}\n\n=== RESPONSE ===\n{text}\n",
            encoding="utf-8")


def extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON in response")
    obj = json.loads(text[start: text.rfind("}" if text[start] == "{" else "]") + 1])
    return obj if isinstance(obj, dict) else {"promos": obj}


def ending_notes(window: list[Episode], ending: dict | None) -> str:
    ending = ending or {}
    tail = ending.get("tail_seconds", 25)
    res_from = ending.get("resolution_from_episode", 10**9)
    notes = []
    for ep in window:
        t0 = max(ep.duration - tail, 0.0)
        if ep.number < res_from:
            notes.append(f"Episode {ep.number} ends at {fmt(ep.duration)}. Its final {tail}s "
                         f"(from {fmt(t0)}) are a planned CLIFFHANGER: prefer a promo ending there.")
        else:
            notes.append(f"Episode {ep.number} ends at {fmt(ep.duration)} and is in the FINALE stretch: "
                         f"its ending may be resolved or happy. Do NOT end a promo on that resolution; "
                         f"prefer a cliffhanger earlier in the episode.")
    return "\n".join(notes)


def propose(llm: LLM, window: list[Episode], n: int = 5, ending: dict | None = None) -> list[Promo]:
    events = "\n".join(e.line() for ep in window for e in ep.events)
    loglines = "\n".join(f"Episode {ep.number}: {ep.logline}" for ep in window)
    user = prompts.PROPOSER_USER.format(
        episodes=", ".join(str(ep.number) for ep in window),
        loglines=loglines, events=events, n=n,
        ending_notes=ending_notes(window, ending))
    tag = "propose_E" + "-".join(str(ep.number) for ep in window)
    data = llm.json(prompts.PROPOSER_SYSTEM, user, tag)
    out = []
    for p in data.get("promos", []):
        try:
            segs = [Segment(int(s["episode"]), str(s["start_id"]), str(s["end_id"]))
                    for s in p["segments"]]
        except (KeyError, TypeError, ValueError):
            continue
        out.append(Promo(segments=segs, hook=p.get("hook", ""),
                         cliffhanger=p.get("cliffhanger", ""), why=p.get("why", ""),
                         scores=p.get("scores", {}), source="llm"))
    return out


def render_clip(promo: Promo, eps: dict[int, Episode]) -> str:
    """What a viewer actually sees/hears - no loglines, no episode context."""
    parts = []
    for k, seg in enumerate(promo.segments):
        if k:
            parts.append("--- CUT TO ---")
        for e in eps[seg.episode].events:
            if e.start >= seg.start - 0.01 and e.start < seg.end - 0.01:
                if e.kind == "DIALOGUE":
                    parts.append(f'{e.speaker}: "{e.text}"')
                elif e.kind == "SOUND FX":
                    parts.append(f"(sound: {e.text})")
                else:
                    parts.append(f"[{e.text}]")
    return "\n".join(parts)


def cold_view(llm: LLM, promo: Promo, eps: dict[int, Episode]) -> dict:
    user = prompts.COLD_VIEWER_USER.format(clip=render_clip(promo, eps))
    return llm.json(prompts.COLD_VIEWER_SYSTEM, user, f"coldview_{promo.id}")
