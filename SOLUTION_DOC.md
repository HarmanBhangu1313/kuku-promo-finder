# Kuku FM – Problem 1: Find the Promos
### Solution Document · *I Married a Broken Soldier. He was a Duke* (50 episodes)

---

## 1. Problem & Assumptions

**Task:** Given the screenplays for 50 episodes of a microdrama, automatically find the best 20–60 second clips to post as TikTok/Reels/Shorts promos. For each clip: episode, exact start/end timestamps, hook, cliffhanger, and a one-line reason. Rank the clips so an editor knows which to post first.

**Assumptions made:**
- Script timestamps match the final video closely enough to cut on (no frame-accurate verification possible from text alone).
- Promos are judged entirely from dialogue and action text; purely visual hooks (a slap with no words) may be under-weighted.
- Shot-start timestamps are safe cut points.
- Earlier-episode promos are preferred: viewers who click land near Episode 1, reducing drop-off.
- A human editor reviews and approves the ranked list before anything is posted.

---

## 2. How It Works

The pipeline has **5 steps**, with a clear split between what AI does and what code enforces:

```
Screenplays (.txt)
      │
      ▼
① PARSER (code)
  Every shot, action, sound effect, and dialogue line
  becomes a timestamped event with a stable ID like "E3-41".

      │
      ▼
② PROPOSER (LLM — gemini-3.5-flash-lite)
  Reads a sliding window of 2 episodes.
  Picks 5 promo candidates per window.
  Returns ONLY event IDs — never timestamps.
  Can stitch 2–3 non-adjacent moments into one clip.

      │
      ▼
③ VALIDATOR (code)
  Maps IDs → real timestamps.
  Snaps to clean shot-cut boundaries.
  Widens cuts that would split a dialogue line mid-sentence.
  Rejects anything < 20s or > 60s, or with invented IDs.

      │
      ▼
④ COLD-VIEWER CHECK (LLM — second call)
  Sees ONLY what plays in the clip, like a TikTok scroller.
  Scores: standalone clarity, would-stop-scrolling, want-to-see-next.

      │
      ▼
⑤ RANKER (code)
  Weighted score. Near-duplicates removed. Max 2 per episode in top list.
```

**Core design rule:** The LLM never writes timestamps. It only names event IDs; code converts them to exact, cut-safe times. This eliminates the most common failure mode — LLMs hallucinating timestamps or cutting mid-sentence.

---

## 3. Ranking Logic

Each promo is scored as:

**Score = 0.35 × hook + 0.35 × cliffhanger + 0.20 × standalone + 0.10 × early_episode − 0.15 × spoiler_risk**

| Weight | Dimension | Rationale |
|---|---|---|
| 35% | Hook | First 3 seconds must stop a scroller — highest leverage |
| 35% | Cliffhanger | Must cut unresolved — drives app opens |
| 20% | Standalone | A stranger must follow the conflict without context |
| 10% | Early episode | Viewer lands near Ep 1 → lower drop-off |
| −15% | Spoiler penalty | Reveals major twists → hurts for new viewers |

An extra bonus applies to promos that end in an episode's final 25 seconds (writers deliberately write cliffhangers there). Near-duplicate clips (IoU > 0.4) are deduplicated; the top list is capped at 2 promos per episode for variety.

---

## 4. Quality Check: Real Numbers & Real Failures

**Run stats (full 50-episode pack):**

| Metric | Value |
|---|---|
| LLM proposer calls | 49 |
| Cold-viewer calls | 20 |
| Total LLM calls | 69 |
| Candidates proposed | 148 |
| Valid after validation | 85 (57%) |
| Rejected by validator | 63 (43%) |
| Top ranked promos | 10 |
| Runtime | ~18.5 minutes |
| Valid clip duration range | 20.3s – 56.5s, avg 34.6s |

**Where the tool picks well:**
- Correctly stitched 3 multi-segment promos where the best dramatic moment was split across a scene cut (e.g. Ep20: villain scheming + ambition payoff = 56.4s stitched clip, score 4.71).
- Surfaced mid-series tension moments (Ep30 witchcraft execution threat, Ep38 prisoner facing gallows) that a keyword search would miss.

**Honest failures (from `rejected.json`):**

| Clip | Problem | AI picked | Code fixed |
|---|---|---|---|
| P003 | Too long | 89.5s — full dramatic arc | ✅ Rejected, human can split |
| P006 | Too long | 151.4s — entire resolution sequence | ✅ Rejected |
| P013 | Too short | 19.5s — just under the 20s floor | ✅ Rejected |
| P016 | Too short | 16.1s — single exchange | ✅ Rejected |

**One place AI got it wrong (real example):**
Clip `P006` in `rejected.json`: the AI proposed Episode 3's entire rescue-and-proposal sequence as one 151-second promo, scoring it hook 5 / cliffhanger 5 / standalone 4. It was the objectively most dramatic moment in the first 5 episodes — but it ran 2.5× the length limit. The model understood *what* to pick but could not reliably count seconds from event timestamps. Moving duration enforcement entirely into code (Step ③) solved this systematically across all 63 rejected clips.

---

## 5. Scale & Cost

| Dimension | Detail |
|---|---|
| Tokens per episode | ~3,000–4,000 (100 events × ~35 tokens each) |
| Episodes per call | 2 (sliding window) |
| Calls for 50 episodes | ~70 total (proposer + cold-viewer) |
| Cost at flash-lite free tier | $0 (within free quota) |
| Cost at paid flash pricing | < $0.05 per show |
| Parallelism | Each show is independent; multiple shows run in parallel |
| Human in the loop | Editor reviews top 10 before any clip is posted |
| Model swap | Change 3 lines in `config.yaml` — no code changes needed |

---

## 6. Tools Used & One Place AI Got It Wrong

**Tools used:**
- `gemini-3.5-flash-lite` via Google AI Studio (free tier, OpenAI-compatible endpoint)
- Python 3.11, `openai` SDK, `streamlit`, `pyyaml`
- Streamlit Community Cloud for deployment

**One place AI got it wrong (from my actual run):**
Clip `P006` in `rejected.json`: the AI proposed Episode 3's entire rescue-and-proposal sequence as one 151-second promo, scoring it hook 5 / cliffhanger 5 / standalone 4. It was the objectively most dramatic moment in the first 5 episodes — but it ran 2.5× the length limit. The model understood *what* to pick but could not reliably count seconds. Moving duration enforcement entirely into code solved this across all 63 rejected clips.
