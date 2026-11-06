"""Deterministic parser for the Kuku screenplay format. No AI here.

Each episode becomes an ordered list of events. Every event gets a stable ID
like "E3-41" so the LLM can refer to moments by ID instead of inventing
timestamps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

NON_DIALOGUE = {"CAMERA", "ACTION", "SOUND FX"}

HEADER_RE = re.compile(r"^\*\*(.+?):\*\*\s*$")
TIME_RE = re.compile(r"Start:\s*\((\d+):(\d+(?:\.\d+)?)\)\s*\|\s*End:\s*\((\d+):(\d+(?:\.\d+)?)\)")
EP_RE = re.compile(r"EPISODE NUMBER:\s*Episode\s*(\d+)", re.I)
SCENE_RE = re.compile(r"^SCENE\s+(\d+)", re.I)


def to_sec(m: str, s: str) -> float:
    return int(m) * 60 + float(s)


def fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


@dataclass
class Event:
    id: str
    episode: int
    idx: int
    scene: int
    kind: str          # CAMERA | ACTION | SOUND FX | DIALOGUE
    speaker: str       # "" for non-dialogue
    modifiers: list[str]
    start: float
    end: float
    text: str

    def line(self) -> str:
        """Compact one-line form used in prompts."""
        who = self.speaker if self.kind == "DIALOGUE" else self.kind
        mods = f" ({', '.join(self.modifiers)})" if self.modifiers else ""
        return f"[{self.id} {fmt(self.start)}-{fmt(self.end)}] {who}{mods}: {self.text}"


@dataclass
class Episode:
    number: int
    logline: str
    continuity: str
    duration: float
    events: list[Event] = field(default_factory=list)
    source: str = ""

    def to_dict(self):
        d = asdict(self)
        return d


def parse_header(h: str):
    h = h.strip()
    if h.upper() in NON_DIALOGUE:
        return h.upper(), "", []
    mods = re.findall(r"\(([^)]*)\)", h)
    speaker = re.sub(r"\s*\([^)]*\)", "", h).strip()
    return "DIALOGUE", speaker, [m.strip() for m in mods]


def parse_episode(text: str, source: str = "") -> Episode:
    lines = text.splitlines()
    num_m = EP_RE.search(text)
    number = int(num_m.group(1)) if num_m else -1
    logline = _field(text, "EPISODE LOGLINE")
    continuity = _field(text, "CONTINUITY NOTES")

    events: list[Event] = []
    scene = 0
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        sm = SCENE_RE.match(line)
        if sm:
            scene = int(sm.group(1))
        hm = HEADER_RE.match(line)
        if hm and i + 1 < len(lines):
            tm = TIME_RE.search(lines[i + 1])
            if tm:
                kind, speaker, mods = parse_header(hm.group(1))
                body = []
                j = i + 2
                while j < len(lines) and lines[j].strip() and not HEADER_RE.match(lines[j].strip()):
                    body.append(lines[j].strip())
                    j += 1
                txt = " ".join(body).strip()
                if kind == "DIALOGUE":
                    txt = txt.strip('"').strip("“”")
                events.append(Event(
                    id=f"E{number}-{len(events)}", episode=number, idx=len(events),
                    scene=scene, kind=kind, speaker=speaker, modifiers=mods,
                    start=to_sec(tm.group(1), tm.group(2)),
                    end=to_sec(tm.group(3), tm.group(4)), text=txt,
                ))
                i = j
                continue
        i += 1

    duration = max((e.end for e in events), default=0.0)
    return Episode(number, logline, continuity, duration, events, source)


def _field(text: str, name: str) -> str:
    m = re.search(rf"{name}:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def load_dir(path: str | Path) -> list[Episode]:
    eps = []
    for p in sorted(Path(path).glob("*.txt")):
        eps.append(parse_episode(p.read_text(encoding="utf-8"), p.name))
    eps.sort(key=lambda e: e.number)
    return eps


def shot_starts(ep: Episode) -> list[float]:
    """Clean cut points = start of every CAMERA shot."""
    return sorted({e.start for e in ep.events if e.kind == "CAMERA"} | {0.0})


def shot_ends(ep: Episode) -> list[float]:
    return sorted({e.end for e in ep.events if e.kind == "CAMERA"} | {ep.duration})
