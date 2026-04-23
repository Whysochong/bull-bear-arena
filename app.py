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
            ticker = st.text_input("Ticker", placeholder="AAPL", max_chars=10).strip().upper()
        with col2:
            notes = st.text_area(
                "Optional context (breaking news, earnings, etc.)",
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
            st.session_state.error = str(e)
            st.session_state.phase = "idle"
            status.update(label=f"Failed: {e}", state="error")

    st.rerun()


def main() -> None:
    _startup_check()
    _init_session_state()

    if st.session_state.phase == "idle":
        if st.session_state.error:
            st.error(st.session_state.error)
            st.session_state.error = None
        render_form()
    elif st.session_state.phase == "running":
        render_running()
    else:
        st.info("Results panel wired up in the next task.")


if __name__ == "__main__":
    main()
