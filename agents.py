"""Pipeline orchestration + subprocess wrapper for claude -p agent calls."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Iterable

import prompts as _prompts


AGENT_TIMEOUT_SECONDS = 300  # 5 minutes per agent call
DEFAULT_MODEL = "sonnet"
SPECIALIST_CONCURRENCY = 12  # all 12 specialist agents run in parallel (6 bull + 6 bear)
_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Ordered pipeline. Each entry: (event_key, label, kind, bucket_path)
# kind in {"research", "fact_check", "analyst_bull", "analyst_bear",
#          "head_bull", "head_bear", "judge", "price_target"}
_PIPELINE: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("researcher",         "🔎 Researching…",                  "research",     ("researcher",)),
    ("fact_checker",       "✅ Fact-checking…",                "fact_check",   ("researcher",)),
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
    ("head_bull",          "👔 Head Bull synthesizing…",       "head_bull",    ("headBull",)),
    ("head_bear",          "👔 Head Bear synthesizing…",       "head_bear",    ("headBear",)),
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
    model: str,
) -> list[str]:
    argv = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--system-prompt", system_prompt,
        "--tools", " ".join(tools) if tools else "",
    ]
    # `--tools` is variadic; use `--` to end options before the prompt positional
    argv += ["--", user_prompt]
    return argv


def _looks_like_rate_limit(stderr: str) -> bool:
    s = stderr.lower()
    return "429" in s or "rate limit" in s or "rate_limit" in s


def _run_with_retry(argv: list[str], *, attempts: int = 2, wait_s: int = 30):
    for attempt in range(attempts):
        with tempfile.TemporaryDirectory(prefix="bba-") as clean_cwd:
            try:
                proc = subprocess.run(
                    argv,
                    cwd=clean_cwd,
                    capture_output=True,
                    text=True,
                    timeout=AGENT_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as e:
                raise AgentError(
                    f"claude -p timed out after {AGENT_TIMEOUT_SECONDS}s"
                ) from e
        if proc.returncode == 0:
            return proc
        if not _looks_like_rate_limit(proc.stderr):
            return proc
        if attempt + 1 < attempts:
            time.sleep(wait_s)
    # All attempts exhausted — return the final proc so caller raises AgentError
    return proc


def run_agent(
    system_prompt: str,
    user_prompt: str,
    *,
    tools: Iterable[str] | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Run a single claude -p call and return the assistant's text response."""
    argv = _build_argv(system_prompt, user_prompt, tools=tools, model=model)

    proc = _run_with_retry(argv)

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
    """Run a claude -p call expecting raw JSON output; return the parsed dict.

    The CLI's ``--json-schema`` flag triggers a tool-use flow whose textual
    ``result`` is a prose summary rather than the structured data, so we
    append the schema to the system prompt instead and parse ``result`` as JSON.
    """
    augmented_system = (
        f"{system_prompt}\n\n"
        f"You MUST respond with ONLY a single JSON object matching this JSON Schema. "
        f"No markdown code fences. No prose before or after. Just the JSON object.\n\n"
        f"{json.dumps(schema, indent=2)}"
    )
    argv = _build_argv(
        augmented_system, user_prompt,
        tools=None, model=model,
    )

    proc = _run_with_retry(argv)

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


def _fact_checker_prompt(ticker: str, researcher_text: str) -> str:
    today = datetime.now().date().isoformat()
    return (
        f"Ticker: {ticker}\n"
        f"Date: {today}\n\n"
        f"Researcher's draft brief:\n\n{researcher_text}\n\n"
        f"Verify every numeric claim above using WebSearch. Return the revised "
        f"brief as instructed."
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


def _head_prompt(ticker: str, side_specialists: dict[str, str], side: str) -> str:
    today = datetime.now().date().isoformat()
    block = "\n\n".join(f"=== {k.upper()} ===\n{v}" for k, v in side_specialists.items())
    return (
        f"Ticker: {ticker}\nDate: {today}\n\n"
        f"Here are the six {side} specialist analyses:\n\n{block}\n\n"
        f"Synthesize them into your unified lead {side} advocacy brief as instructed."
    )


def _judge_prompt(ticker: str, head_bull: str, head_bear: str) -> str:
    today = datetime.now().date().isoformat()
    return (
        f"Ticker: {ticker}\nDate: {today}\n\n"
        f"=== LEAD BULL ADVOCATE ===\n{head_bull}\n\n"
        f"=== LEAD BEAR ADVOCATE ===\n{head_bear}\n\n"
        f"Produce the clash JSON."
    )


def _price_target_prompt(
    ticker: str, researcher_text: str,
    head_bull: str, head_bear: str,
    clash: dict,
) -> str:
    today = datetime.now().date().isoformat()
    return (
        f"Ticker: {ticker}\nDate: {today}\n\n"
        f"Researcher brief: {researcher_text}\n\n"
        f"=== LEAD BULL ADVOCATE ===\n{head_bull}\n\n"
        f"=== LEAD BEAR ADVOCATE ===\n{head_bear}\n\n"
        f"=== JUDGE VERDICT ===\n"
        f"Winner: {clash.get('winner', '?')}  Score: {clash.get('verdict', '?')}/10\n"
        f"Summary: {clash.get('summary', '')}\n\n"
        f"Produce the price target JSON."
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_debate(ticker: str, notes: str = ""):
    """Generator: run the full 17-agent pipeline, yielding progress events.

    Phases:
      1. Researcher (sequential, WebSearch)
      2. 12 specialists in parallel (SPECIALIST_CONCURRENCY workers)
      3. Head Bull + Head Bear in parallel (synthesize their side's specialists)
      4. Judge (reads the two head briefs only)
      5. Price target (reads researcher + heads + judge verdict)

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
        "headBull": "",
        "headBear": "",
        "clash": {},
        "priceTarget": {},
    }
    total = len(_PIPELINE)
    step_counter = 0

    def _bump_step() -> int:
        nonlocal step_counter
        step_counter += 1
        return step_counter

    # --- Phase 1: Researcher (sequential, WebSearch) ---------------------
    r_key, r_label, _, _ = _PIPELINE[0]
    r_step = _bump_step()
    yield {"type": "agent_start", "key": r_key, "label": r_label,
           "step": r_step, "total": total}
    try:
        researcher_text = run_agent(
            _prompts.SYSTEM_PROMPTS[r_key],
            _researcher_prompt(ticker, notes),
            tools=["WebSearch"],
        )
    except AgentError as e:
        researcher_text = f"n/a — researcher failed: {e}"
    debate["researcher"] = researcher_text
    yield {"type": "agent_complete", "key": r_key, "text": researcher_text,
           "step": r_step, "total": total}

    # --- Phase 1b: Fact-checker (sequential, WebSearch) ------------------
    fc_key, fc_label, _, _ = _PIPELINE[1]
    fc_step = _bump_step()
    yield {"type": "agent_start", "key": fc_key, "label": fc_label,
           "step": fc_step, "total": total}
    try:
        fact_checked = run_agent(
            _prompts.SYSTEM_PROMPTS[fc_key],
            _fact_checker_prompt(ticker, researcher_text),
            tools=["WebSearch"],
        )
        debate["researcher"] = fact_checked  # vetted version replaces raw
    except AgentError as e:
        # Fact-checker failure is non-fatal — keep the raw researcher text
        fact_checked = f"(fact-checker failed: {e}) — using raw researcher brief below:\n\n{researcher_text}"
    yield {"type": "agent_complete", "key": fc_key, "text": fact_checked,
           "step": fc_step, "total": total}

    # --- Phase 2: 12 specialists in parallel -----------------------------
    specialist_entries = [
        entry for entry in _PIPELINE
        if entry[2] in ("analyst_bull", "analyst_bear")
    ]
    specialist_steps: dict[str, int] = {}
    for key, label, _kind, _path in specialist_entries:
        specialist_steps[key] = _bump_step()
        yield {"type": "agent_start", "key": key, "label": label,
               "step": specialist_steps[key], "total": total}

    def _run_specialist(entry):
        key, _label, kind, path = entry
        side = "bullish" if kind == "analyst_bull" else "bearish"
        text = run_agent(
            _prompts.SYSTEM_PROMPTS[key],
            _analyst_prompt(ticker, notes, debate["researcher"], side),
        )
        return key, path, text

    with ThreadPoolExecutor(max_workers=SPECIALIST_CONCURRENCY) as pool:
        futures = {pool.submit(_run_specialist, entry): entry[0]
                   for entry in specialist_entries}
        for fut in as_completed(futures):
            key, path, text = fut.result()  # AgentError propagates
            bucket_name, field = path
            debate[bucket_name][field] = text
            yield {"type": "agent_complete", "key": key, "text": text,
                   "step": specialist_steps[key], "total": total}

    # --- Phase 3: Head Bull + Head Bear in parallel ----------------------
    head_entries = [
        entry for entry in _PIPELINE
        if entry[2] in ("head_bull", "head_bear")
    ]
    head_steps: dict[str, int] = {}
    for key, label, _kind, _path in head_entries:
        head_steps[key] = _bump_step()
        yield {"type": "agent_start", "key": key, "label": label,
               "step": head_steps[key], "total": total}

    def _run_head(entry):
        key, _label, kind, path = entry
        if kind == "head_bull":
            side_dict, side = debate["bull"], "bull"
        else:
            side_dict, side = debate["bear"], "bear"
        text = run_agent(
            _prompts.SYSTEM_PROMPTS[key],
            _head_prompt(ticker, side_dict, side),
        )
        return key, path, text

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_run_head, entry): entry[0]
                   for entry in head_entries}
        for fut in as_completed(futures):
            key, path, text = fut.result()
            (field,) = path
            debate[field] = text
            yield {"type": "agent_complete", "key": key, "text": text,
                   "step": head_steps[key], "total": total}

    # --- Phase 4: Judge (sequential, reads the two head briefs) ----------
    j_key, j_label, _, _ = _PIPELINE[-2]
    j_step = _bump_step()
    yield {"type": "agent_start", "key": j_key, "label": j_label,
           "step": j_step, "total": total}
    clash = run_structured_agent(
        _prompts.SYSTEM_PROMPTS[j_key],
        _judge_prompt(ticker, debate["headBull"], debate["headBear"]),
        schema=_prompts.JUDGE_SCHEMA,
    )
    debate["clash"] = clash
    yield {"type": "agent_complete", "key": j_key, "text": json.dumps(clash),
           "step": j_step, "total": total}

    # --- Phase 5: Price target (sequential, depends on judge) ------------
    p_key, p_label, _, _ = _PIPELINE[-1]
    p_step = _bump_step()
    yield {"type": "agent_start", "key": p_key, "label": p_label,
           "step": p_step, "total": total}
    pt = run_structured_agent(
        _prompts.SYSTEM_PROMPTS[p_key],
        _price_target_prompt(
            ticker, debate["researcher"],
            debate["headBull"], debate["headBear"], debate["clash"],
        ),
        schema=_prompts.PRICE_TARGET_SCHEMA,
    )
    debate["priceTarget"] = pt
    yield {"type": "agent_complete", "key": p_key, "text": json.dumps(pt),
           "step": p_step, "total": total}

    yield {"type": "debate_complete", "debate": debate}
