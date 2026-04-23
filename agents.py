"""Pipeline orchestration + subprocess wrapper for claude -p agent calls."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime
from typing import Iterable

import prompts as _prompts


AGENT_TIMEOUT_SECONDS = 300  # 5 minutes per agent call
DEFAULT_MODEL = "sonnet"
_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Ordered pipeline. Each entry: (event_key, label, kind, bucket_path)
# kind in {"research", "analyst_bull", "analyst_bear", "judge", "price_target"}
_PIPELINE: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("researcher",         "🔎 Researching…",                  "research",     ("researcher",)),
    ("bull_fundamentals",  "📊 Bull Fundamentals…",            "analyst_bull", ("bull", "fundamentals")),
    ("bull_growth",        "🚀 Bull Growth Catalysts…",        "analyst_bull", ("bull", "growth")),
    ("bull_macro",         "🌍 Bull Macro Tailwinds…",         "analyst_bull", ("bull", "macro")),
    ("bull_moat",          "🏰 Bull Moat & Pricing…",          "analyst_bull", ("bull", "moat")),
    ("bull_capital",       "💎 Bull Capital Allocation…",      "analyst_bull", ("bull", "capital")),
    ("bull_technicals",    "📈 Bull Technicals…",              "analyst_bull", ("bull", "technicals")),
    ("bear_risk",          "⚠️ Bear Risk Factors…",             "analyst_bear", ("bear", "risk")),
    ("bear_valuation",     "💰 Bear Valuation…",               "analyst_bear", ("bear", "valuation")),
    ("bear_headwinds",     "🌪️ Bear Macro Headwinds…",          "analyst_bear", ("bear", "headwinds")),
    ("bear_disruption",    "🎯 Bear Disruption…",              "analyst_bear", ("bear", "disruption")),
    ("bear_accounting",    "🚩 Bear Accounting & Sentiment…",  "analyst_bear", ("bear", "accounting")),
    ("bear_technicals",    "📉 Bear Technicals…",              "analyst_bear", ("bear", "technicals")),
    ("judge",              "⚖️ Judging…",                      "judge",        ("clash",)),
    ("price_target",       "🎯 Building price target…",        "price_target", ("priceTarget",)),
]


class AgentError(RuntimeError):
    """Raised when a claude -p subprocess fails or its output is unparseable."""


def _build_argv(
    system_prompt: str,
    user_prompt: str,
    *,
    tools: Iterable[str] | None,
    json_schema: dict | None,
    model: str,
) -> list[str]:
    argv = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--system-prompt", system_prompt,
        "--tools", " ".join(tools) if tools else "",
    ]
    if json_schema is not None:
        argv += ["--json-schema", json.dumps(json_schema)]
    argv.append(user_prompt)
    return argv


def run_agent(
    system_prompt: str,
    user_prompt: str,
    *,
    tools: Iterable[str] | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Run a single claude -p call and return the assistant's text response."""
    argv = _build_argv(system_prompt, user_prompt, tools=tools, json_schema=None, model=model)

    with tempfile.TemporaryDirectory(prefix="bba-") as clean_cwd:
        proc = subprocess.run(
            argv,
            cwd=clean_cwd,
            capture_output=True,
            text=True,
            timeout=AGENT_TIMEOUT_SECONDS,
        )

    if proc.returncode != 0:
        raise AgentError(
            f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:500]}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise AgentError(f"claude -p returned non-JSON stdout: {e}") from e

    result = payload.get("result")
    if not isinstance(result, str):
        raise AgentError(f"claude -p output missing 'result' string: {repr(payload)[:300]}")
    return result


def run_structured_agent(
    system_prompt: str,
    user_prompt: str,
    *,
    schema: dict,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run a claude -p call with --json-schema; return the parsed JSON dict."""
    argv = _build_argv(
        system_prompt, user_prompt,
        tools=None, json_schema=schema, model=model,
    )

    with tempfile.TemporaryDirectory(prefix="bba-") as clean_cwd:
        proc = subprocess.run(
            argv,
            cwd=clean_cwd,
            capture_output=True,
            text=True,
            timeout=AGENT_TIMEOUT_SECONDS,
        )

    if proc.returncode != 0:
        raise AgentError(
            f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:500]}"
        )

    try:
        outer = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise AgentError(f"claude -p returned non-JSON stdout: {e}") from e

    inner_text = outer.get("result")
    if not isinstance(inner_text, str):
        raise AgentError(f"claude -p output missing 'result' string: {repr(outer)[:300]}")

    cleaned = _MD_FENCE.sub("", inner_text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AgentError(f"agent returned unparseable JSON: {e}\nraw: {repr(inner_text)[:300]}") from e


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _researcher_prompt(ticker: str, notes: str) -> str:
    today = datetime.now().date().isoformat()
    notes_block = f"\nUser notes: {notes}\n" if notes.strip() else ""
    return (
        f"Ticker: {ticker}\n"
        f"Date: {today}\n"
        f"{notes_block}\n"
        f"Research this stock using WebSearch and return the prose paragraph as instructed."
    )


def _analyst_prompt(ticker: str, notes: str, researcher_text: str, side: str) -> str:
    today = datetime.now().date().isoformat()
    notes_block = f"\nUser notes: {notes}\n" if notes.strip() else ""
    return (
        f"Ticker: {ticker}\n"
        f"Date: {today}\n"
        f"{notes_block}"
        f"Researcher brief: {researcher_text}\n\n"
        f"Make your {side} case from your specialty alone."
    )


def _judge_prompt(ticker: str, bull: dict[str, str], bear: dict[str, str]) -> str:
    today = datetime.now().date().isoformat()
    bull_block = "\n\n".join(f"{k.upper()}: {v}" for k, v in bull.items())
    bear_block = "\n\n".join(f"{k.upper()}: {v}" for k, v in bear.items())
    return (
        f"Ticker: {ticker}\nDate: {today}\n\n"
        f"=== BULL ANALYSES ===\n{bull_block}\n\n"
        f"=== BEAR ANALYSES ===\n{bear_block}\n\n"
        f"Produce the clash JSON."
    )


def _price_target_prompt(
    ticker: str, researcher_text: str,
    bull: dict[str, str], bear: dict[str, str],
    clash: dict,
) -> str:
    today = datetime.now().date().isoformat()
    bull_block = "\n\n".join(f"{k.upper()}: {v}" for k, v in bull.items())
    bear_block = "\n\n".join(f"{k.upper()}: {v}" for k, v in bear.items())
    return (
        f"Ticker: {ticker}\nDate: {today}\n\n"
        f"Researcher brief: {researcher_text}\n\n"
        f"=== BULL ANALYSES ===\n{bull_block}\n\n"
        f"=== BEAR ANALYSES ===\n{bear_block}\n\n"
        f"=== JUDGE VERDICT ===\n"
        f"Winner: {clash['winner']}  Score: {clash['verdict']}/10\n"
        f"Summary: {clash['summary']}\n\n"
        f"Produce the price target JSON."
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_debate(ticker: str, notes: str = ""):
    """Generator: run the full 15-agent pipeline, yielding progress events.

    Final event is {'type': 'debate_complete', 'debate': {...}}.
    """
    ticker = ticker.upper().strip()
    debate: dict = {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "notes": notes,
        "researcher": "",
        "bull": {},
        "bear": {},
        "clash": {},
        "priceTarget": {},
    }
    total = len(_PIPELINE)

    for step, (key, label, kind, path) in enumerate(_PIPELINE, start=1):
        yield {"type": "agent_start", "key": key, "label": label, "step": step, "total": total}

        try:
            if kind == "research":
                text = run_agent(
                    _prompts.SYSTEM_PROMPTS[key],
                    _researcher_prompt(ticker, notes),
                    tools=["WebSearch"],
                )
                debate["researcher"] = text
                emitted = text

            elif kind in ("analyst_bull", "analyst_bear"):
                side = "bullish" if kind == "analyst_bull" else "bearish"
                text = run_agent(
                    _prompts.SYSTEM_PROMPTS[key],
                    _analyst_prompt(ticker, notes, debate["researcher"], side),
                )
                bucket_name, field = path
                debate[bucket_name][field] = text
                emitted = text

            elif kind == "judge":
                clash = run_structured_agent(
                    _prompts.SYSTEM_PROMPTS[key],
                    _judge_prompt(ticker, debate["bull"], debate["bear"]),
                    schema=_prompts.JUDGE_SCHEMA,
                )
                debate["clash"] = clash
                emitted = json.dumps(clash)

            elif kind == "price_target":
                pt = run_structured_agent(
                    _prompts.SYSTEM_PROMPTS[key],
                    _price_target_prompt(
                        ticker, debate["researcher"],
                        debate["bull"], debate["bear"], debate["clash"],
                    ),
                    schema=_prompts.PRICE_TARGET_SCHEMA,
                )
                debate["priceTarget"] = pt
                emitted = json.dumps(pt)

            else:
                raise RuntimeError(f"unknown pipeline kind: {kind}")

        except AgentError as e:
            if kind == "research":
                debate["researcher"] = f"n/a — researcher failed: {e}"
                emitted = debate["researcher"]
            else:
                raise

        yield {"type": "agent_complete", "key": key, "text": emitted,
               "step": step, "total": total}

    yield {"type": "debate_complete", "debate": debate}
