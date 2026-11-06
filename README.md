# 🎬 Microdrama Promo Finder (Kuku Assignment - Problem 1)

An automated AI-powered tool that analyzes episodic vertical microdrama screenplays and discovers, validates, and ranks high-converting **20–60 second promo clips** for platforms like TikTok, YouTube Shorts, and Instagram Reels.

---

## 🌟 Highlights & Architecture

The system features a hybrid **AI + Deterministic Code pipeline** with strict quality safeguards:

1. **Deterministic Parser (`promo/parser.py`)**: Parses raw screenplays into structured, timestamped events with stable IDs (e.g., `E3-41`), tracking camera shots, sound effects, actions, and spoken dialogue.
2. **LLM Proposer (`promo/llm.py`)**: Leverages LLMs (`gemini-3.5-flash-lite`, swappable via `config.yaml`) across sliding multi-episode windows to identify strong narrative hooks, cliffhangers, and multi-segment stitched promos.
   - *Core Rule*: The model only proposes moment IDs; it **never invents or outputs raw timestamps**.
3. **Cut-Safe Validator (`promo/validate.py`)**: Converts IDs to exact shot-boundary timestamps, dynamically widens cuts to avoid chopping dialogue mid-sentence, and strictly rejects clips outside the 20–60s duration window.
4. **Cold-Viewer Evaluator (`promo/llm.py`)**: A secondary LLM evaluation that views the isolated clip script with zero prior context, assessing standalone comprehensibility, scroll-stopping power, and binge desire.
5. **Multi-Factor Ranker (`promo/rank.py`)**: Computes weighted scores factoring in hook potency (35%), cliffhanger tension (35%), standalone clarity (20%), episode positioning bonus (10%), and spoiler penalties (-15%), while deduplicating near-identical candidate segments.

---

## 📂 Repository Structure

```text
├── app.py                   # Interactive Streamlit Web UI
├── run.py                   # CLI entrypoint for batch runs
├── eval.py                  # Evaluation benchmark against ground-truth labels
├── config.yaml              # Model, endpoint, thresholds & ranking weights
├── requirements.txt         # Minimal Python dependencies
├── SOLUTION_DOC.md          # 2-Page architectural & benchmark solution doc
├── labels_template.csv      # Evaluation labeling template
├── .streamlit/
│   ├── config.toml          # Custom dark UI styling
│   └── secrets.toml.example # Template for Streamlit Cloud secrets
├── promo/                   # Core pipeline modules
│   ├── parser.py            # Screenplay ingestion & shot segmentation
│   ├── prompts.py           # Structured prompt templates
│   ├── llm.py               # OpenAI-compatible LLM client & cold-viewer
│   ├── heuristic.py         # Fast offline fallback / baseline engine
│   ├── validate.py          # Boundary enforcement & cut safety rules
│   ├── rank.py              # Multi-objective ranking & deduplication
│   └── pipeline.py          # End-to-end orchestration
└── tests/
    └── test_pipeline.py     # Offline unit test suite with mock LLM
```

---

## 🚀 Quickstart

### 1. Installation
```bash
git clone <your-repo-url>
cd <repo-folder>
pip install -r requirements.txt
```

### 2. Environment Setup
Get a free API key from [Google AI Studio](https://aistudio.google.com/):
```bash
export GEMINI_API_KEY="your-api-key"
```
*(Any OpenAI-compatible endpoint works: Groq, OpenRouter, Ollama, OpenAI by editing `config.yaml`)*

### 3. Running via Interactive Web UI
```bash
streamlit run app.py
```
- Upload your episode screenplay `.txt` files directly in the browser or run off local `./data/`.
- Inspect top ranked clips, hook/cliffhanger breakdowns, and cold-viewer metrics.
- Export results directly as CSV/JSON/Markdown.

### 4. Running via CLI
```bash
# Full LLM pipeline
python run.py --data data --out outputs/full_run

# Quick smoke test on specific episodes
python run.py --episodes 1-5 --out outputs/smoke

# Zero-API heuristic baseline
python run.py --mode heuristic --data data --out outputs/baseline
```

---

## 🧪 Evaluation & Quality Metrics

Compare pipeline outputs against manual editor selections:
```bash
python eval.py --labels labels.csv --pred outputs/full_run/promos_ranked.json
```

---

## 🌐 Free Streamlit Community Cloud Deployment

1. Push this repository to GitHub (all confidential screenplays & `.env`/secrets are ignored by `.gitignore`).
2. Go to [share.streamlit.io](https://share.streamlit.io/) and create a new app selecting `app.py`.
3. In **Settings -> Secrets**, add:
   ```toml
   GEMINI_API_KEY = "your_actual_api_key"
   ```
