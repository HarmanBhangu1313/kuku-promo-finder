"""Streamlit demo: streamlit run app.py
Works locally and on Streamlit Community Cloud.
On Cloud, set GEMINI_API_KEY in Streamlit Secrets.
"""
import json
import os
import tempfile
from pathlib import Path

import streamlit as st
import yaml

from promo.parser import parse_episode, load_dir
from promo.pipeline import run, segs_str

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Kuku Promo Finder",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load config ───────────────────────────────────────────────────────────────
cfg = yaml.safe_load(Path("config.yaml").read_text())

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    st.subheader("Model")
    mode = st.selectbox(
        "Picker mode",
        ["llm", "heuristic", "both"],
        index=["llm", "heuristic", "both"].index(cfg.get("mode", "llm")),
        help="**llm** = AI picks (best quality). **heuristic** = rule-based, no API key needed. **both** = run both and merge.",
    )

    cfg["llm"]["base_url"] = st.text_input(
        "Base URL (OpenAI-compatible)",
        cfg["llm"]["base_url"],
        help="Gemini, Groq, OpenRouter, Ollama, OpenAI — all work.",
    )
    cfg["llm"]["model"] = st.text_input("Model name", cfg["llm"]["model"])

    # Key: sidebar input OR env var (for Streamlit Cloud secrets)
    env_key = os.environ.get(cfg["llm"].get("api_key_env", "GEMINI_API_KEY"), "")
    key = st.text_input(
        "API key",
        value="",
        type="password",
        help="Leave blank to use the server env var / Streamlit secret.",
        placeholder="Paste key or leave blank if set server-side",
    )
    if key:
        os.environ["PROMO_UI_KEY"] = key
        cfg["llm"]["api_key_env"] = "PROMO_UI_KEY"

    st.subheader("Run options")
    cfg["window"] = st.selectbox(
        "Episodes per LLM call",
        [1, 2],
        index=cfg.get("window", 2) - 1,
        help="2 lets the AI stitch moments across adjacent episodes.",
    )
    cfg["cold_viewer"] = st.checkbox(
        "Cold-viewer check",
        value=cfg.get("cold_viewer", True),
        help="A second AI call sees only the clip (no context) and rates it as a TikTok scroller would.",
    )

    st.subheader("Clip length")
    min_len, max_len = st.slider(
        "Allowed duration (seconds)", 10, 90, (20, 60), step=5
    )
    cfg.setdefault("promo", {})["min_len"] = min_len
    cfg["promo"]["max_len"] = max_len

    st.divider()
    st.caption("Built for Kuku FM · PS1 submission")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🎬 Kuku Promo Finder")
st.markdown(
    "Upload microdrama screenplays and get **ranked 20–60 s promo clips** "
    "ready for TikTok / Reels / Shorts — with hook, cliffhanger, and a cold-viewer score."
)

# ── File input ────────────────────────────────────────────────────────────────
col_up, col_local = st.columns([2, 1])
with col_up:
    files = st.file_uploader(
        "Upload episode screenplays (.txt)",
        type="txt",
        accept_multiple_files=True,
        help="Upload any number of episode .txt files in Kuku screenplay format.",
    )
with col_local:
    st.markdown("**or**")
    use_local = st.checkbox(
        "Use episodes in `./data/`",
        value=(not files),
        help="Pre-loaded 50-episode pack (local run only).",
    )

# Episode range filter
ep_range = st.text_input(
    "Episode range (optional)",
    placeholder="e.g. 1-10 to run a subset",
    help="Leave blank to process all uploaded/local files.",
)

# ── Run button ────────────────────────────────────────────────────────────────
run_col, clear_col = st.columns([1, 5])
with run_col:
    go = st.button("▶ Find promos", type="primary", use_container_width=True)
with clear_col:
    if st.button("🗑 Clear results", use_container_width=False):
        st.session_state.pop("res", None)
        st.session_state.pop("out", None)
        st.rerun()

if go:
    # Load episodes
    if files and not use_local:
        eps = sorted(
            [parse_episode(f.read().decode("utf-8"), f.name) for f in files],
            key=lambda e: e.number,
        )
    else:
        eps = load_dir("data")

    # Optional range filter
    if ep_range.strip():
        try:
            a, b = map(int, ep_range.strip().split("-"))
            eps = [e for e in eps if a <= e.number <= b]
        except ValueError:
            st.error("Episode range must be in the form `start-end`, e.g. `1-10`.")
            st.stop()

    if not eps:
        st.error("No episodes loaded. Upload files or put them in `./data/`.")
        st.stop()

    out = Path(tempfile.mkdtemp(prefix="promos_"))
    status = st.status(
        f"🤖 Running on {len(eps)} episode(s) in **{mode}** mode…",
        expanded=True,
    )
    with status:
        res = run(eps, cfg, out, mode=mode, log=lambda m: st.write(f"`{m}`"))
    status.update(label="✅ Done!", state="complete", expanded=False)
    st.session_state["res"] = res
    st.session_state["out"] = out
    st.balloons()

# ── Results ───────────────────────────────────────────────────────────────────
if "res" in st.session_state:
    res = st.session_state["res"]
    out = st.session_state["out"]
    meta = res["meta"]

    # Metrics strip
    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("🎞 Episodes", len(meta["episodes"]))
    m2.metric("🔍 Candidates", meta["candidates"])
    m3.metric("✅ Valid", meta["valid"])
    m4.metric("❌ Rejected", meta["rejected"])
    m5.metric("🤖 LLM calls", meta["llm_calls"])

    st.caption(
        f"Model: `{meta.get('model') or 'heuristic'}` · "
        f"Mode: `{meta['mode']}` · "
        f"Runtime: `{meta['seconds']:.1f}s`"
    )

    # ── Top promos ────────────────────────────────────────────────────────────
    st.subheader("🏆 Post These First")
    if not res["top"]:
        st.info("No promos passed validation. Try a wider episode range or heuristic mode.")
    for rank, p in enumerate(res["top"], 1):
        seg_label = segs_str(p)
        n_segs = len(p.segments)
        stitch_badge = "🔗 stitched" if n_segs > 1 else ""
        with st.expander(
            f"**#{rank}** · {seg_label} · `{p.duration}s` · score `{p.final_score}` {stitch_badge}"
        ):
            left, right = st.columns([3, 2])
            with left:
                st.markdown(f"**🪝 Hook**\n> {p.hook}")
                st.markdown(f"**🎣 Cliffhanger**\n> {p.cliffhanger}")
                st.markdown(f"**💡 Why it works**\n> {p.why}")
                if p.warnings:
                    st.warning("⚠ " + " · ".join(p.warnings))
            with right:
                if p.cold_view and p.cold_view.get("who_and_what"):
                    st.markdown("**👁 Cold-viewer verdict**")
                    st.info(p.cold_view["who_and_what"])
                    scores = {k: p.cold_view.get(k) for k in
                              ["standalone", "would_stop_scrolling", "want_to_see_next"]
                              if p.cold_view.get(k)}
                    if scores:
                        cv1, cv2, cv3 = st.columns(3)
                        cv1.metric("Standalone", f"{scores.get('standalone', '–')}/5")
                        cv2.metric("Stop scroll", f"{scores.get('would_stop_scrolling', '–')}/5")
                        cv3.metric("Want more", f"{scores.get('want_to_see_next', '–')}/5")
                    confused = p.cold_view.get("confused_by", "")
                    if confused:
                        st.caption(f"⚠ Confused by: {confused}")

    # ── Other valid promos ────────────────────────────────────────────────────
    if res.get("rest"):
        with st.expander(f"📋 Other valid promos ({len(res['rest'])} clips)"):
            for p in res["rest"]:
                st.markdown(
                    f"- `{segs_str(p)}` · {p.duration}s · score {p.final_score} · {p.hook[:80]}…"
                )

    # ── Rejected ──────────────────────────────────────────────────────────────
    with st.expander(f"🚫 Rejected by validator ({len(res['rejected'])} clips)"):
        for p, reasons in res["rejected"]:
            st.markdown(f"- `{p.id}` ({p.source}) · **{'; '.join(reasons)}** · {p.hook[:70]}…")

    # ── Downloads ─────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📥 Download Outputs")
    dl1, dl2, dl3, dl4 = st.columns(4)
    for col, name in zip([dl1, dl2, dl3, dl4],
                         ["report.md", "promos_ranked.csv",
                          "promos_ranked.json", "rejected.json"]):
        fpath = out / name
        if fpath.exists():
            col.download_button(
                f"⬇ {name}",
                fpath.read_bytes(),
                file_name=name,
                use_container_width=True,
            )
