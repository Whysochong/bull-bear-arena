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


def main() -> None:
    _startup_check()
    _init_session_state()

    if st.session_state.phase == "idle":
        render_form()
    elif st.session_state.phase == "running":
        st.info(f"Running debate for {st.session_state._pending_ticker}… (wired up in the next task)")
    else:
        st.info("Results panel wired up in the next task.")


if __name__ == "__main__":
    main()
