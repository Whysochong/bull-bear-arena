"""Bull vs Bear Arena — Streamlit UI."""

from __future__ import annotations

import shutil

import streamlit as st

import agents
import storage


st.set_page_config(page_title="Bull vs Bear Arena", page_icon="⚔️", layout="wide")


def _startup_check() -> None:
    if shutil.which("claude") is None:
        st.error(
            "`claude` CLI not found on PATH. Install Claude Code and run "
            "`claude` once interactively to sign in before using this app."
        )
        st.stop()


def _init_session_state() -> None:
    ss = st.session_state
    ss.setdefault("phase", "idle")      # idle | running | done
    ss.setdefault("progress", 0)        # 0..15
    ss.setdefault("progress_label", "")
    ss.setdefault("current_stream_text", "")
    ss.setdefault("debate", None)       # final debate dict
    ss.setdefault("error", None)


def render_form() -> None:
    st.title("⚔️ Bull vs Bear Arena")
    st.caption("15 Claude agents debate your ticker and produce a verdict + price target.")

    with st.form("debate_form", clear_on_submit=False):
        col1, col2 = st.columns([1, 3])
        with col1:
            ticker = st.text_input(
                "Ticker",
                value=st.session_state.get("_pending_ticker", ""),
                placeholder="AAPL", max_chars=10,
            ).strip().upper()
        with col2:
            notes = st.text_area(
                "Optional context (breaking news, earnings, etc.)",
                value=st.session_state.get("_pending_notes", ""),
                placeholder="Optional — paste any context you want every agent to see.",
                height=80,
            )
        submitted = st.form_submit_button("Debate", type="primary")

    if submitted and ticker:
        st.session_state.phase = "running"
        st.session_state.progress = 0
        st.session_state.progress_label = ""
        st.session_state.current_stream_text = ""
        st.session_state.debate = None
        st.session_state.error = None
        st.session_state._pending_ticker = ticker
        st.session_state._pending_notes = notes
        st.rerun()


def render_running() -> None:
    ticker = st.session_state._pending_ticker
    notes = st.session_state._pending_notes
    st.header(f"⚔️ Debating {ticker}")

    progress_bar = st.progress(0.0, text="Starting…")
    with st.status("Running 15-agent pipeline…", expanded=True) as status:
        live_text = st.empty()
        try:
            for event in agents.run_debate(ticker, notes=notes):
                if event["type"] == "agent_start":
                    st.write(f"**{event['step']}/{event['total']}** — {event['label']}")
                    progress_bar.progress(
                        (event["step"] - 1) / event["total"],
                        text=event["label"],
                    )
                elif event["type"] == "agent_complete":
                    progress_bar.progress(
                        event["step"] / event["total"],
                        text=f"{event['step']}/{event['total']} done",
                    )
                    live_text.markdown(f"> {event['text'][:400]}…" if len(event["text"]) > 400 else f"> {event['text']}")
                elif event["type"] == "debate_complete":
                    debate = event["debate"]
                    storage.save_debate(debate)
                    st.session_state.debate = debate
                    st.session_state.phase = "done"
            status.update(label="Debate complete.", state="complete")
        except agents.AgentError as e:
            st.session_state.error = (
                f"{e}\n\nTip: the ticker and your notes are still filled in on the form — "
                f"just click Debate again to retry."
            )
            st.session_state.phase = "idle"
            status.update(label=f"Failed: {e}", state="error")

    st.rerun()


BULL_KEYS = [
    ("fundamentals", "📊 Fundamentals"),
    ("growth",       "🚀 Growth Catalysts"),
    ("macro",        "🌍 Macro Tailwinds"),
    ("moat",         "🏰 Moat & Pricing Power"),
    ("capital",      "💎 Capital Allocation"),
    ("technicals",   "📈 Technicals"),
]
BEAR_KEYS = [
    ("risk",         "⚠️ Risk Factors"),
    ("valuation",    "💰 Valuation"),
    ("headwinds",    "🌪️ Macro Headwinds"),
    ("disruption",   "🎯 Disruption & Obsolescence"),
    ("accounting",   "🚩 Accounting & Sentiment"),
    ("technicals",   "📉 Technicals"),
]


def _upside_pct(current: float | None, target: float | None) -> str:
    if not current or current <= 0 or target is None:
        return "—"
    pct = (target - current) / current * 100
    return f"{pct:+.1f}%"


def _render_verdict(clash: dict) -> None:
    winner = clash.get("winner", "?")
    verdict = clash.get("verdict", "?")
    summary = clash.get("summary", "")
    color = "#00e676" if winner == "BULL" else "#ff5252"
    st.markdown(
        f"<div style='padding:16px;border-radius:12px;background:{color}20;"
        f"border:1px solid {color}'>"
        f"<h2 style='margin:0;color:{color}'>{winner} · {verdict}/10</h2>"
        f"<p style='margin:8px 0 0'>{summary}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_price_target(pt: dict) -> None:
    st.subheader("🎯 12-month price target")
    current = pt.get("currentPrice")
    ev = pt.get("expectedValue")
    bear_p = pt.get("bearCase", {}).get("price")
    bull_p = pt.get("bullCase", {}).get("price")

    c1, c2, c3 = st.columns(3)
    c1.metric("Current", f"${current:.2f}" if current else "n/a")
    c2.metric("Expected", f"${ev:.2f}" if ev is not None else "n/a", _upside_pct(current, ev))
    c3.metric("Range", f"${bear_p:.0f} – ${bull_p:.0f}" if bear_p and bull_p else "n/a")

    base_p = pt.get("baseCase", {}).get("price")
    if current and bear_p and bull_p and base_p:
        st.markdown(
            f"`Bear ${bear_p:.0f}` ── `Now ${current:.0f}` ── `Base ${base_p:.0f}` ── `Bull ${bull_p:.0f}`"
        )

    with st.expander("Price target methodology & scenarios"):
        st.write(f"**Methodology:** {pt.get('methodology', '')}")
        st.write(f"**Horizon:** {pt.get('timeHorizon', '')}")
        for label, key in (("Bull case", "bullCase"), ("Base case", "baseCase"), ("Bear case", "bearCase")):
            case = pt.get(key, {})
            prob = case.get("probability", 0) * 100
            st.write(f"**{label}:** ${case.get('price', 0):.2f} · {prob:.0f}% prob · {case.get('reasoning', '')}")


def _render_clash(clash: dict) -> None:
    st.subheader("⚔️ Clash points")
    for i, cp in enumerate(clash.get("clashPoints", []), start=1):
        with st.expander(f"{i}. {cp.get('topic', '')} — winner: {cp.get('winner', '?')}"):
            st.markdown(f"**Bull:** {cp.get('bull', '')}")
            st.markdown(f"**Bear:** {cp.get('bear', '')}")
            st.markdown(f"**Why {cp.get('winner', '?')} wins:** {cp.get('reasoning', '')}")


def _render_agents(bull: dict, bear: dict) -> None:
    st.subheader("Specialist arguments")
    left, right = st.columns(2)
    with left:
        st.markdown("### :green[Bull]")
        for key, label in BULL_KEYS:
            with st.expander(label):
                st.write(bull.get(key, "(no output)"))
    with right:
        st.markdown("### :red[Bear]")
        for key, label in BEAR_KEYS:
            with st.expander(label):
                st.write(bear.get(key, "(no output)"))


def render_result(debate: dict) -> None:
    st.header(f"⚔️ {debate['ticker']} · {debate['timestamp'][:16].replace('T', ' ')}")
    _render_verdict(debate.get("clash", {}))
    _render_price_target(debate.get("priceTarget", {}))
    _render_clash(debate.get("clash", {}))
    _render_agents(debate.get("bull", {}), debate.get("bear", {}))

    with st.expander("🔎 Researcher findings"):
        st.write(debate.get("researcher", ""))

    if st.button("New debate"):
        st.session_state.phase = "idle"
        st.session_state.debate = None
        st.rerun()


def _load_debate_from_path(path) -> None:
    debate = storage.load_debate(path)
    st.session_state.debate = debate
    st.session_state.phase = "done"


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Past debates")
        entries = storage.list_debates()
        if not entries:
            st.caption("No debates yet. Run one from the form.")
        else:
            for entry in entries:
                ts = entry["timestamp"][:16].replace("T", " ")
                label = f"{entry['ticker']} · {ts} · {entry['winner']} {entry['verdict']}"
                if entry.get("expectedValue") is not None:
                    label += f" · ${entry['expectedValue']:.0f}"
                if st.button(label, key=f"load-{entry['path']}"):
                    _load_debate_from_path(entry["path"])
                    st.rerun()

            st.divider()
            if st.button("🗑️ Clear history"):
                st.session_state._confirm_clear = True
            if st.session_state.get("_confirm_clear"):
                st.warning("Delete every saved debate?")
                c1, c2 = st.columns(2)
                if c1.button("Yes, delete"):
                    storage.clear_debates()
                    st.session_state._confirm_clear = False
                    st.rerun()
                if c2.button("Cancel"):
                    st.session_state._confirm_clear = False
                    st.rerun()


def main() -> None:
    _startup_check()
    _init_session_state()
    render_sidebar()

    if st.session_state.phase == "idle":
        if st.session_state.error:
            st.error(st.session_state.error)
            st.session_state.error = None
        render_form()
    elif st.session_state.phase == "running":
        render_running()
    else:
        render_result(st.session_state.debate)


if __name__ == "__main__":
    main()
