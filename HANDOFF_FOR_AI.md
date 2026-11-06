# Project handoff: Kuku Promo Finder (Problem 1)

> **For the AI assistant reading this:** you are picking up an existing,
> working project. Use this file as the source of truth for what exists, how it
> works, and what is left to do. Do not redesign the architecture or rewrite
> working modules unless the user asks. Make small, targeted changes, and
> explain each one so the user can defend it in an interview. The user must
> make the product decisions (ranking weights, prompt wording, what counts as
> a good promo); offer options and trade-offs rather than deciding for them.

---

## 1. The assignment (summary)

Kuku (a microdrama company) gave an AI Generalist assignment. The user chose
**Problem 1: Find the Promos.**

- Input: screenplays for the first 50 episodes of one English show (US
  audience). Each episode is a `.txt` file with a timestamp on every camera
  shot, action, sound effect and line of dialogue.
- Build a tool that finds promos: **20–60 second clips** cut from the show,
  posted on TikTok/Reels/Shorts to pull in new viewers.
- A good promo:
  1. **Hook:** something in the first 3 seconds that stops a scroller (a
     slap, a reveal, a shocking line).
  2. **Cliffhanger:** cuts at an unresolved moment.
  3. **Standalone:** makes sense to someone who has never seen the show.
  - Usually one continuous stretch, but may join a few moments from one
    episode or across several.
- For each promo, output: episode, start and end timestamp of every segment
  (in order), the hook, the cliffhanger, and one line on why it works.
- Also: **rank** the promos (which to post first, and why) and **check
  quality** (where the tool picks badly).
- Only find clips. No editing, music or text overlays.

**Submission (one form):**
| Item | Required | Notes |
|---|---|---|
| Solution doc | Yes | PDF, max 2 pages |
| Prototype link | Yes | Deployed app (Streamlit Community Cloud is free), GitHub repo, or Colab |
| Raw outputs | Yes | Unedited output folder from running on the **full 50-episode pack** |
| Walkthrough video | Optional, recommended | Max 3 min, screen recording in own voice |

**Rules that matter:**
- 48-hour deadline from when the brief was sent. No late submissions.
- No questions allowed. Make assumptions and write them in the doc.
- Any AI tools allowed. The doc must say **which tools were used and one
  place where they got it wrong.**
- Free tiers only. If a paid API would help, describe it and build a smaller
  free version.
- Shortlisted candidates **rerun the solution on a new input in the
  interview**, possibly with a stronger model Kuku connects via API. An easily
  swappable model is valued.
- The input pack is confidential. Do not publish it (keep it out of public
  repos).
- Very similar submissions from the same campus get reviewed closely. The work
  must be the user's own, and they must understand all of it.

**Grading lenses:** problem framing and assumptions; approach and scale (what
goes to AI vs code vs human, cost at volume); quality checking with real runs
and honest failures; a prototype that runs on real inputs; clear, short
communication.

---

## 2. Input format (verified on episodes 1–4)

```
EPISODE NUMBER: Episode 3
EPISODE LOGLINE: ...
CONTINUITY NOTES: ...

--- SCRIPT START ---

SCENE 01
Scene heading: INT. CATHEDRAL NAVE – DAY
Scene start: 00:00.00
Scene end: 00:22.80

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:03.50)
Medium shot on Lady Juliana ...

**LADY IN GOLD GOWN (Mocking, Spiteful):**
Start: (00:02.10) | End: (00:04.20)
"Look at you..."
```

- Block types: `CAMERA`, `ACTION`, `SOUND FX`, or a speaker name with
  parenthetical tone modifiers (`(O.S.)`, `(V.O.)`, `(Off-screen)` may appear).
- Timestamps are `MM:SS.ss`, relative to the episode start.
- Dialogue lines often continue across shots (`"I can..."` then
  `"...when your family..."`).
- Episodes run about 1:50–2:30.
- The show (episodes 1–4): Lady Juliana is jilted at the altar by Gerald for
  her sister Clarissa; her family disowns her; a scarred stranger rescues her,
  proposes, and marries her.

---

## 3. What has been built

### Folder layout
```
promo_finder/
├── run.py               CLI entry point
├── app.py               Streamlit web UI
├── eval.py              Recall vs hand-picked promos (temporal IoU)
├── config.yaml          Model, mode, lengths, ranking weights
├── requirements.txt     openai, pyyaml, streamlit
├── labels_template.csv  Template for hand-picked promos
├── HANDOFF_FOR_AI.md    This file
├── data/                Episode .txt files go here (not committed)
├── outputs/             One folder per run
├── tests/test_pipeline.py  Offline test with a fake model
└── promo/
    ├── parser.py        Screenplay -> Episode/Event objects
    ├── model.py         Promo and Segment dataclasses
    ├── heuristic.py     Rule-based proposer (no API key needed)
    ├── prompts.py       All LLM prompts
    ├── llm.py           OpenAI-compatible client, proposer, cold-viewer
    ├── validate.py      Turns IDs into times, snaps cuts, enforces rules
    ├── rank.py          Scoring, de-duplication, diversity cap
    └── pipeline.py      Wires it together and writes outputs
```

### Pipeline
1. **Parse (code).** `parser.py` turns each episode into an ordered list of
   `Event`s: `id` (`E{episode}-{index}`, e.g. `E3-41`), `kind`, `speaker`,
   `modifiers`, `start`, `end`, `text`.
2. **Propose (LLM, or rules).** `llm.propose()` sends a window of episodes
   (default 2 adjacent episodes, so it can stitch across them) as compact lines
   like `[E3-93 01:50.90-01:52.50] LADY JULIANA (Whispering): Why are you doing
   this?`. The model returns JSON promos with 1+ segments defined by
   `start_id`/`end_id`, plus hook, cliffhanger, why, and scores (`hook`,
   `cliffhanger`, `standalone` 1–5; `spoiler_risk` 0–5).
   `heuristic.propose()` is a keyword-based fallback and baseline.
3. **Validate (code).** `validate.py`:
   - looks up IDs and rejects unknown ones ("model invented it");
   - snaps start down to a CAMERA shot start and end up to a shot end;
   - widens the cut if it would split a line of dialogue;
   - enforces 20–60s total; rejects overlapping segments;
   - warns if nothing but a camera shot happens in the first 3s (visual-only hook).
4. **Cold-viewer check (LLM).** `llm.cold_view()` shows a second call only
   what plays in the clip (no loglines, no context) and asks who/what it is
   about, what is confusing, and 1–5 scores for standalone,
   would-stop-scrolling, want-to-see-next.
5. **Rank (code).** `rank.py` score =
   `0.35*hook + 0.35*cliffhanger + 0.2*standalone + 0.1*early_episode − 0.15*spoiler_risk`
   (proposer and cold-viewer scores are averaged). Then it removes near-
   duplicates (overlap > 0.4) and caps the top list at 2 promos per episode.
   Weights are in `config.yaml`.

### Core design rule (keep this)
**The LLM never writes timestamps.** It only names event IDs; code converts
them to exact, cut-safe times. This removes invented timestamps and mid-line
cuts.

### Model swap
`config.yaml` → `llm.base_url`, `llm.model`, `llm.api_key_env`. Any
OpenAI-compatible endpoint (Gemini default, Groq, OpenRouter, Ollama, OpenAI,
or Kuku's API). Check the provider's docs for the current model name.

### Outputs per run
`promos_ranked.json/.csv`, `report.md`, `promos_other_valid.json`,
`rejected.json` (with reasons), `llm_logs/` (raw prompts and responses),
`run_meta.json` (counts, model, calls, runtime).

---

## 4. What has been tested

- Parser on episodes 1–4: 95 / 74 / 118 / 110 events.
- Heuristic mode on episodes 1–4: 48 candidates, 48 valid, top 8 ranked
  (`outputs/heuristic_4eps/`).
- Offline LLM-path test (`python -m tests.test_pipeline`) with a fake model:
  a stitched 2-segment promo passes (33.85s); an invented ID and an overlong
  clip are both rejected; a dialogue line crossing a shot cut is not split.
- Streamlit app runs end to end in heuristic mode.
- **Not yet done: a run with a real LLM.** No API key was available.

## 5. Known failure modes (observed on episodes 1–4)

1. **Best moment exceeds 60s.** Ep3, guard punch (01:24) through proposal
   (02:25.75), is about 62s continuous. The heuristic misses it; only a stitched
   promo (punch + ring) fits.
2. **Inconsistent character labels.** Juliana / Lady Juliana; Clarissa / Lady
   in Gold Gown; Gerald / The Former Groom; the father as Blond Nobleman; the
   stepmother as Matriarch / Noble Matriarch / Off-screen Voice / Lady Ashcroft;
   The Bearded Stranger / Mysterious Bearded Man. This affects standalone
   checks and any per-character logic. A possible fix is an alias map in config.
3. **Ending on resolution.** The heuristic gives episode endings a bonus, so it
   ranks Ep4's ending (the couple walks out, resolved) as a cliffhanger.
4. **Visual-only hooks.** Slaps or punches with no line read weakly in text.
5. **Heuristic hook picking** sometimes chooses a reaction (a gasp) over the
   stronger line in the same 3 seconds.

---

## 6. What is left to do (in order)

1. `pip install -r requirements.txt`; get a free Gemini API key; set
   `GEMINI_API_KEY`.
2. Smoke test: `python run.py --episodes 1-5 --out outputs/smoke`. Read
   `report.md` and `rejected.json`. If the model's JSON or model name breaks,
   fix the config or prompt.
3. Full run: `python run.py --data data --out outputs/full_run`. This folder
   is the **raw outputs** submission. Do not edit it.
4. Hand-label 10–15 good promos into `labels.csv`, then run
   `python eval.py --labels labels.csv --pred outputs/full_run/promos_ranked.json`
   and also against `promos_other_valid.json`. Report recall.
5. Optionally run `--mode heuristic` on all 50 and compare it with the LLM as a baseline.
6. Review the top 10 by hand. Note where the tool picks badly (wrong cut,
   spoiler, confusing out of context).
7. Possible improvements, only if time allows and the user wants them:
   character alias map; a spoiler check across the whole show; hook strength
   scored on the first 3 seconds only.
8. Deploy `app.py` on Streamlit Community Cloud. Keep `data/*.txt` out of the
   public repo; users upload files through the UI.
9. Write the 2-page doc: problem and assumptions; how it works (AI vs code vs
   human editor); ranking logic; quality checks with real numbers; failures;
   scale and cost; tools used + **one place AI got it wrong** (from the
   user's own experience, e.g. something in `rejected.json`).
10. Record an optional 3-minute walkthrough.

## 7. Assumptions to state in the doc
- Script timestamps match the final video closely enough to cut on.
- Promos are judged from text; visual-only moments may be under-weighted.
- Shot starts are safe cut points.
- Earlier-episode promos are preferred (fewer spoilers, viewers land near Ep 1).
- A human editor approves the top list before posting.
