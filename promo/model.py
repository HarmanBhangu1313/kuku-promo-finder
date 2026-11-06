from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Segment:
    episode: int
    start_id: str
    end_id: str
    start: float = 0.0   # filled by validator (snapped to shot cuts)
    end: float = 0.0


@dataclass
class Promo:
    segments: list[Segment]
    hook: str = ""
    cliffhanger: str = ""
    why: str = ""
    # 1-5 scores from the proposer (LLM or heuristic); spoiler_risk is 0-5
    scores: dict = field(default_factory=dict)
    source: str = ""            # "llm" | "heuristic"
    warnings: list[str] = field(default_factory=list)
    cold_view: dict = field(default_factory=dict)
    final_score: float = 0.0
    id: str = ""

    @property
    def duration(self) -> float:
        return round(sum(s.end - s.start for s in self.segments), 2)

    @property
    def episodes(self) -> list[int]:
        return sorted({s.episode for s in self.segments})

    def to_dict(self):
        d = asdict(self)
        d["duration"] = self.duration
        return d
