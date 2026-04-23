# Bull vs Bear Arena Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Streamlit app that runs a 15-agent stock debate via `claude -p` subprocess calls and displays verdicts + a quantitative price target, with past debates persisted as JSON on disk.

**Architecture:** Single Streamlit process. Four Python modules: `prompts.py` (15 personas + 2 JSON schemas), `agents.py` (subprocess wrapper + orchestrator generator), `storage.py` (filesystem helpers), `app.py` (Streamlit UI). Subprocess calls run from a clean temp cwd to avoid picking up the user's `~/CLAUDE.md`. Subscription auth, no API key.

**Tech Stack:** Python 3.11+, Streamlit ≥ 1.36, `claude` CLI ≥ 2.1, pytest, `unittest.mock` (stdlib) for subprocess mocking.

**Spec:** `docs/specs/2026-04-23-bull-bear-arena-design.md`

---

## Task 1: Environment setup + test harness

**Files:**
- Create: `requirements.txt` (already exists — add pytest)
- Create: `conftest.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Add pytest to requirements.txt**

Replace contents of `requirements.txt`:

```
streamlit>=1.36
pytest>=8.0
```

- [ ] **Step 2: Create a Python 3.11+ venv and install**

Run from project root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: `Successfully installed streamlit-* pytest-*`.

- [ ] **Step 3: Create conftest.py so pytest finds project-root modules**

Create `conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
```

- [ ] **Step 4: Create empty test package marker**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 5: Write a smoke test to verify pytest runs**

Create `tests/test_smoke.py`:

```python
def test_pytest_works():
    assert 1 + 1 == 2
```

- [ ] **Step 6: Run the smoke test**

Run from project root: `python -m pytest tests/ -v`
Expected: `tests/test_smoke.py::test_pytest_works PASSED` and `1 passed`.

- [ ] **Step 7: Verify the claude CLI is callable**

Run: `claude -p "respond with just the word ok" --output-format json --model sonnet`
Expected: JSON printed to stdout with a `"result"` field whose value contains `"ok"` (case-insensitive). If this fails with an auth error, the user needs to run `claude` once interactively to sign in.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: pytest harness + env setup"
```

---

## Task 2: prompts.py — 15 personas + 2 JSON schemas

**Files:**
- Create: `prompts.py`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_prompts.py`:

```python
import prompts


def test_all_15_personas_defined():
    expected = {
        "researcher",
        "bull_fundamentals", "bull_growth", "bull_macro",
        "bull_moat", "bull_capital", "bull_technicals",
        "bear_risk", "bear_valuation", "bear_headwinds",
        "bear_disruption", "bear_accounting", "bear_technicals",
        "judge", "price_target",
    }
    assert set(prompts.SYSTEM_PROMPTS.keys()) == expected


def test_each_persona_is_nonempty_string():
    for name, text in prompts.SYSTEM_PROMPTS.items():
        assert isinstance(text, str), f"{name} not a string"
        assert len(text.strip()) > 50, f"{name} suspiciously short"


def test_schemas_are_valid_json_schema_dicts():
    for name in ("JUDGE_SCHEMA", "PRICE_TARGET_SCHEMA"):
        schema = getattr(prompts, name)
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema
        assert "required" in schema


def test_judge_schema_shape():
    s = prompts.JUDGE_SCHEMA
    props = s["properties"]
    assert set(s["required"]) >= {"clashPoints", "winner", "verdict", "summary"}
    assert props["winner"]["enum"] == ["BULL", "BEAR"]
    assert props["verdict"]["type"] == "integer"


def test_price_target_schema_shape():
    s = prompts.PRICE_TARGET_SCHEMA
    props = s["properties"]
    assert set(s["required"]) >= {
        "currentPrice", "bullCase", "baseCase", "bearCase",
        "expectedValue", "timeHorizon", "methodology",
    }
    for case in ("bullCase", "baseCase", "bearCase"):
        case_props = props[case]["properties"]
        assert set(case_props.keys()) >= {"price", "probability", "reasoning"}
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: `ModuleNotFoundError: No module named 'prompts'`.

- [ ] **Step 3: Create prompts.py**

Create `prompts.py`:

```python
"""System prompts and JSON schemas for every agent in the Bull vs Bear Arena."""

SYSTEM_PROMPTS: dict[str, str] = {
    "researcher": (
        "You are a financial research assistant. Use WebSearch to gather the "
        "latest facts about the given stock ticker: current share price (USD), "
        "market cap, trailing P/E, forward P/E, revenue (TTM), revenue growth "
        "rate, operating margin, notable recent news from the last 90 days. "
        "Respond with a single flowing prose paragraph (no markdown, no bullets, "
        "no headings). Start the paragraph with the current share price as a "
        "numeric USD value (e.g. 'Current price: $180.50.'). Keep it under 250 "
        "words. If WebSearch fails, say so explicitly in one sentence."
    ),
    "bull_fundamentals": (
        "You are a BULL Fundamentals Analyst. Analyze ONLY the company's "
        "financial fundamentals: earnings growth, revenue trajectory, margins, "
        "balance sheet strength, cash flow, and ROE/ROIC. Make the strongest "
        "bullish case from fundamentals alone. Be specific with numbers where "
        "possible. 2-3 short paragraphs max. No markdown, no bullets — flowing "
        "prose only."
    ),
    "bull_growth": (
        "You are a BULL Growth Catalyst Analyst. Analyze ONLY growth drivers: "
        "new products, TAM expansion, innovation pipeline, market share gains, "
        "AI/tech adoption, international expansion, and competitive advantages. "
        "Make the strongest bullish case from growth catalysts alone. 2-3 short "
        "paragraphs. No markdown, prose only."
    ),
    "bull_macro": (
        "You are a BULL Macro/Sector Analyst. Analyze ONLY macro and "
        "sector-level tailwinds: industry growth trends, favorable regulation, "
        "sector rotation opportunities, economic conditions that benefit this "
        "company, and secular trends. Make the strongest bullish case from macro "
        "factors alone. 2-3 short paragraphs. No markdown, prose only."
    ),
    "bull_moat": (
        "You are a BULL Moat & Pricing Power Analyst. Analyze ONLY durable "
        "competitive advantages: network effects, switching costs, brand equity, "
        "intellectual property, scale advantages, and ability to raise prices. "
        "Make the strongest bullish case from moat alone. 2-3 short paragraphs. "
        "No markdown, prose only."
    ),
    "bull_capital": (
        "You are a BULL Capital Allocation & Insider Signal Analyst. Analyze "
        "ONLY capital allocation discipline and insider behavior: share "
        "buybacks at attractive prices, dividend sustainability/growth, "
        "accretive M&A history, insider buying activity, and management's track "
        "record of shareholder value creation. Make the strongest bullish case "
        "from these factors alone. 2-3 short paragraphs. No markdown, prose only."
    ),
    "bull_technicals": (
        "You are a BULL Technicals Analyst. Analyze ONLY technical chart "
        "signals: uptrends, higher-highs/higher-lows, breakouts above "
        "resistance, bullish moving-average crossovers, relative strength vs "
        "the market, and volume confirmation. Make the strongest bullish case "
        "from price action alone. 2-3 short paragraphs. No markdown, prose only."
    ),
    "bear_risk": (
        "You are a BEAR Risk Analyst. Analyze ONLY risks: competitive threats, "
        "execution risk, regulatory/legal exposure, customer concentration, "
        "management concerns, and disruption threats specific to this company. "
        "Make the strongest bearish case from risk factors alone. 2-3 short "
        "paragraphs. No markdown, prose only."
    ),
    "bear_valuation": (
        "You are a BEAR Valuation Analyst. Analyze ONLY valuation concerns: "
        "P/E vs peers, price-to-growth ratios, historical multiple compression "
        "risk, whether growth expectations are already priced in, and DCF "
        "sensitivity. Make the strongest bearish case from valuation alone. "
        "2-3 short paragraphs. No markdown, prose only."
    ),
    "bear_headwinds": (
        "You are a BEAR Macro Headwinds Analyst. Analyze ONLY macro/sector "
        "headwinds: geopolitical risks, interest rate impact, sector "
        "cyclicality, supply chain vulnerabilities, currency risks, and "
        "unfavorable regulatory trends. Make the strongest bearish case from "
        "macro headwinds alone. 2-3 short paragraphs. No markdown, prose only."
    ),
    "bear_disruption": (
        "You are a BEAR Disruption & Obsolescence Analyst. Analyze ONLY "
        "disruption and secular-decline risks: technology shifts that could "
        "obsolete the product, changing consumer habits, new entrants with "
        "structurally better economics, and industry-wide secular decline. "
        "Make the strongest bearish case from disruption alone. 2-3 short "
        "paragraphs. No markdown, prose only."
    ),
    "bear_accounting": (
        "You are a BEAR Accounting & Sentiment Analyst. Analyze ONLY accounting "
        "quality and market sentiment concerns: quality-of-earnings red flags, "
        "aggressive revenue recognition, growing gap between GAAP and non-GAAP, "
        "insider selling, analyst downgrades, declining short interest trends, "
        "and governance issues. Make the strongest bearish case from these "
        "factors alone. 2-3 short paragraphs. No markdown, prose only."
    ),
    "bear_technicals": (
        "You are a BEAR Technicals Analyst. Analyze ONLY bearish technical "
        "signals: downtrends, lower-highs/lower-lows, breakdowns below support, "
        "death crosses, RSI divergence, underperformance vs the market, and "
        "volume weakness. Make the strongest bearish case from price action "
        "alone. 2-3 short paragraphs. No markdown, prose only."
    ),
    "judge": (
        "You are the CHIEF INVESTMENT STRATEGIST presiding over a multi-agent "
        "stock debate. You have received analysis from 12 specialized agents "
        "(6 bull, 6 bear).\n\n"
        "Your job:\n"
        "1. CLASH: Find 2-3 key points where bull and bear directly contradict. "
        "For each, state both sides concisely and pick a winner with reasoning.\n"
        "2. VERDICT: Declare overall winner (BULL or BEAR), score 1-10 "
        "(1=strong sell, 10=strong buy), and a 2-3 sentence summary.\n\n"
        "Respond ONLY with valid JSON matching the provided schema. No markdown "
        "fences, no extra commentary."
    ),
    "price_target": (
        "You are a QUANTITATIVE PRICE TARGET ANALYST. You have received the "
        "researcher's brief (including current share price), 12 specialist "
        "analyses, and the judge's verdict. Produce a 12-month price target "
        "using methodologies appropriate to the stock (forward P/E multiple, "
        "DCF, sum-of-parts, etc.).\n\n"
        "Output three scenarios (bull/base/bear) each with a target price, a "
        "probability (0 to 1), and 1-2 sentences of reasoning. Probabilities "
        "MUST sum to 1.0 (to within 0.01). Compute expectedValue as the "
        "probability-weighted mean of the three prices. State the methodology "
        "briefly.\n\n"
        "Respond ONLY with valid JSON matching the provided schema. No markdown "
        "fences, no extra commentary."
    ),
}


JUDGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "clashPoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "bull": {"type": "string"},
                    "bear": {"type": "string"},
                    "winner": {"type": "string", "enum": ["BULL", "BEAR"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["topic", "bull", "bear", "winner", "reasoning"],
            },
            "minItems": 2,
            "maxItems": 4,
        },
        "winner": {"type": "string", "enum": ["BULL", "BEAR"]},
        "verdict": {"type": "integer", "minimum": 1, "maximum": 10},
        "summary": {"type": "string"},
    },
    "required": ["clashPoints", "winner", "verdict", "summary"],
}


PRICE_TARGET_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "currentPrice": {"type": "number"},
        "bullCase": {
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "probability": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
            },
            "required": ["price", "probability", "reasoning"],
        },
        "baseCase": {
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "probability": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
            },
            "required": ["price", "probability", "reasoning"],
        },
        "bearCase": {
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "probability": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
            },
            "required": ["price", "probability", "reasoning"],
        },
        "expectedValue": {"type": "number"},
        "timeHorizon": {"type": "string"},
        "methodology": {"type": "string"},
    },
    "required": [
        "currentPrice", "bullCase", "baseCase", "bearCase",
        "expectedValue", "timeHorizon", "methodology",
    ],
}
```

- [ ] **Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add prompts.py tests/test_prompts.py
git commit -m "feat: 15 agent personas + judge/price-target JSON schemas"
```

---

## Task 3: agents.py — `run_agent` subprocess wrapper

**Files:**
- Create: `agents.py`
- Create: `tests/test_agents.py`

Background: `run_agent` spawns `claude -p` as a subprocess and returns the assistant's text response. Runs from a clean temp cwd so Claude Code's CLAUDE.md ancestor-walk doesn't pick up the user's `~/CLAUDE.md`. Optional `tools` list controls `--tools` flag (empty list = no tools).

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents.py`:

```python
import json
from unittest.mock import MagicMock, patch

import agents


def _fake_proc(result_text: str, returncode: int = 0, stderr: str = ""):
    """Build a fake CompletedProcess mimicking `claude -p --output-format json`."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = json.dumps({"type": "result", "subtype": "success", "result": result_text})
    proc.stderr = stderr
    return proc


@patch("agents.subprocess.run")
def test_run_agent_returns_result_text(mock_run):
    mock_run.return_value = _fake_proc("hello response")
    text = agents.run_agent("sys", "user")
    assert text == "hello response"


@patch("agents.subprocess.run")
def test_run_agent_passes_core_flags(mock_run):
    mock_run.return_value = _fake_proc("ok")
    agents.run_agent("sys prompt", "user msg")

    argv = mock_run.call_args[0][0]
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "--model" in argv and argv[argv.index("--model") + 1] == "sonnet"
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
    assert "--system-prompt" in argv and argv[argv.index("--system-prompt") + 1] == "sys prompt"
    # User prompt is the final positional arg
    assert argv[-1] == "user msg"


@patch("agents.subprocess.run")
def test_run_agent_disables_tools_by_default(mock_run):
    mock_run.return_value = _fake_proc("ok")
    agents.run_agent("sys", "user")
    argv = mock_run.call_args[0][0]
    assert "--tools" in argv
    # default tools list is empty string → no tools
    assert argv[argv.index("--tools") + 1] == ""


@patch("agents.subprocess.run")
def test_run_agent_enables_requested_tool(mock_run):
    mock_run.return_value = _fake_proc("ok")
    agents.run_agent("sys", "user", tools=["WebSearch"])
    argv = mock_run.call_args[0][0]
    assert argv[argv.index("--tools") + 1] == "WebSearch"


@patch("agents.subprocess.run")
def test_run_agent_runs_from_clean_cwd(mock_run):
    mock_run.return_value = _fake_proc("ok")
    agents.run_agent("sys", "user")
    kwargs = mock_run.call_args.kwargs
    assert "cwd" in kwargs
    # Must not be a path under the user's home (where CLAUDE.md lives)
    assert not str(kwargs["cwd"]).startswith("/Users/") or "/tmp" in str(kwargs["cwd"])


@patch("agents.subprocess.run")
def test_run_agent_raises_on_nonzero_exit(mock_run):
    mock_run.return_value = _fake_proc("", returncode=1, stderr="boom")
    try:
        agents.run_agent("sys", "user")
    except agents.AgentError as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("expected AgentError")


@patch("agents.subprocess.run")
def test_run_agent_raises_on_malformed_json(mock_run):
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "not json at all"
    proc.stderr = ""
    mock_run.return_value = proc

    try:
        agents.run_agent("sys", "user")
    except agents.AgentError:
        pass
    else:
        raise AssertionError("expected AgentError")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_agents.py -v`
Expected: `ModuleNotFoundError: No module named 'agents'`.

- [ ] **Step 3: Implement `run_agent`**

Create `agents.py`:

```python
"""Pipeline orchestration + subprocess wrapper for claude -p agent calls."""

from __future__ import annotations

import json
import subprocess
import tempfile
from typing import Iterable


AGENT_TIMEOUT_SECONDS = 300  # 5 minutes per agent call
DEFAULT_MODEL = "sonnet"


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
        raise AgentError(f"claude -p output missing 'result' string: {payload!r}")
    return result
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_agents.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents.py tests/test_agents.py
git commit -m "feat: run_agent subprocess wrapper with isolated cwd"
```

---

## Task 4: agents.py — `run_structured_agent` (JSON-schema output)

**Files:**
- Modify: `agents.py` (add function)
- Modify: `tests/test_agents.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agents.py`:

```python
@patch("agents.subprocess.run")
def test_run_structured_agent_parses_json_result(mock_run):
    inner = {"winner": "BULL", "verdict": 8, "summary": "s", "clashPoints": []}
    mock_run.return_value = _fake_proc(json.dumps(inner))
    out = agents.run_structured_agent(
        "sys", "user",
        schema={"type": "object", "properties": {}, "required": []},
    )
    assert out == inner


@patch("agents.subprocess.run")
def test_run_structured_agent_passes_schema_flag(mock_run):
    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    mock_run.return_value = _fake_proc('{"x": "y"}')
    agents.run_structured_agent("sys", "user", schema=schema)

    argv = mock_run.call_args[0][0]
    assert "--json-schema" in argv
    passed = json.loads(argv[argv.index("--json-schema") + 1])
    assert passed == schema


@patch("agents.subprocess.run")
def test_run_structured_agent_strips_markdown_fences(mock_run):
    # Defensive: if the model wraps JSON in ```json ... ``` despite the schema
    mock_run.return_value = _fake_proc('```json\n{"winner": "BEAR"}\n```')
    out = agents.run_structured_agent(
        "sys", "user",
        schema={"type": "object", "properties": {}, "required": []},
    )
    assert out == {"winner": "BEAR"}


@patch("agents.subprocess.run")
def test_run_structured_agent_raises_on_unparseable_result(mock_run):
    mock_run.return_value = _fake_proc("not json")
    try:
        agents.run_structured_agent(
            "sys", "user",
            schema={"type": "object", "properties": {}, "required": []},
        )
    except agents.AgentError:
        pass
    else:
        raise AssertionError("expected AgentError")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_agents.py -v`
Expected: 4 new tests fail with `AttributeError: module 'agents' has no attribute 'run_structured_agent'`.

- [ ] **Step 3: Add the function**

Append to `agents.py`:

```python
import re

_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


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
        raise AgentError(f"claude -p output missing 'result' string: {outer!r}")

    cleaned = _MD_FENCE.sub("", inner_text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AgentError(f"agent returned unparseable JSON: {e}\nraw: {inner_text!r}") from e
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_agents.py -v`
Expected: all tests pass (11 total across both test files' agent tests).

- [ ] **Step 5: Commit**

```bash
git add agents.py tests/test_agents.py
git commit -m "feat: run_structured_agent for JSON-schema outputs"
```

---

## Task 5: agents.py — `run_debate` orchestrator

**Files:**
- Modify: `agents.py` (add orchestrator)
- Modify: `tests/test_agents.py` (add tests)

Background: `run_debate(ticker, notes)` is a generator that yields progress events and, as its final event, the assembled debate dict. It makes 15 sequential calls: researcher (with WebSearch) → 6 bull → 6 bear → judge (schema) → price target (schema). Agent results are accumulated and fed into later prompts.

Event shapes:
- `{"type": "agent_start", "key": "bull_fundamentals", "label": "📊 Bull Fundamentals…", "step": 2, "total": 15}`
- `{"type": "agent_complete", "key": "bull_fundamentals", "text": "…", "step": 2, "total": 15}`
- `{"type": "debate_complete", "debate": {...full dict matching data model...}}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agents.py`:

```python
AGENT_SEQUENCE = [
    "researcher",
    "bull_fundamentals", "bull_growth", "bull_macro",
    "bull_moat", "bull_capital", "bull_technicals",
    "bear_risk", "bear_valuation", "bear_headwinds",
    "bear_disruption", "bear_accounting", "bear_technicals",
    "judge", "price_target",
]


@patch("agents.run_structured_agent")
@patch("agents.run_agent")
def test_run_debate_emits_all_events_in_order(mock_text, mock_struct):
    mock_text.return_value = "stub analysis"
    mock_struct.side_effect = [
        {"clashPoints": [], "winner": "BULL", "verdict": 7, "summary": "ok"},
        {
            "currentPrice": 100.0,
            "bullCase": {"price": 120, "probability": 0.3, "reasoning": "r1"},
            "baseCase": {"price": 110, "probability": 0.5, "reasoning": "r2"},
            "bearCase": {"price": 90,  "probability": 0.2, "reasoning": "r3"},
            "expectedValue": 109.0,
            "timeHorizon": "12 months",
            "methodology": "multiples",
        },
    ]

    events = list(agents.run_debate("AAPL", notes=""))
    starts = [e for e in events if e["type"] == "agent_start"]
    completes = [e for e in events if e["type"] == "agent_complete"]
    finals = [e for e in events if e["type"] == "debate_complete"]

    assert [e["key"] for e in starts] == AGENT_SEQUENCE
    assert [e["key"] for e in completes] == AGENT_SEQUENCE
    assert len(finals) == 1
    # Progress counters are 1-indexed and span 1..15
    assert [e["step"] for e in starts] == list(range(1, 16))
    assert all(e["total"] == 15 for e in starts)


@patch("agents.run_structured_agent")
@patch("agents.run_agent")
def test_run_debate_feeds_researcher_into_sub_agents(mock_text, mock_struct):
    mock_text.side_effect = lambda system, user, **kw: (
        "Current price: $180. RESEARCHER_OUTPUT" if "research" in system.lower()
        else f"PROMPT_CONTAINED:{int('RESEARCHER_OUTPUT' in user)}"
    )
    mock_struct.side_effect = [
        {"clashPoints": [], "winner": "BULL", "verdict": 7, "summary": "ok"},
        {
            "currentPrice": 180.0,
            "bullCase": {"price": 200, "probability": 0.3, "reasoning": "r"},
            "baseCase": {"price": 190, "probability": 0.5, "reasoning": "r"},
            "bearCase": {"price": 170, "probability": 0.2, "reasoning": "r"},
            "expectedValue": 189.0,
            "timeHorizon": "12 months",
            "methodology": "m",
        },
    ]

    events = list(agents.run_debate("AAPL", notes=""))
    completes = {e["key"]: e["text"] for e in events if e["type"] == "agent_complete"}
    # Every non-researcher text agent must have seen the researcher output in its prompt
    for key in AGENT_SEQUENCE[1:13]:  # 12 specialists
        assert completes[key] == "PROMPT_CONTAINED:1", f"{key} did not receive researcher context"


@patch("agents.run_structured_agent")
@patch("agents.run_agent")
def test_run_debate_assembles_data_model(mock_text, mock_struct):
    mock_text.return_value = "stub"
    clash = {"clashPoints": [], "winner": "BEAR", "verdict": 3, "summary": "s"}
    pt = {
        "currentPrice": 50.0,
        "bullCase": {"price": 60, "probability": 0.3, "reasoning": "r"},
        "baseCase": {"price": 55, "probability": 0.5, "reasoning": "r"},
        "bearCase": {"price": 40, "probability": 0.2, "reasoning": "r"},
        "expectedValue": 53.5,
        "timeHorizon": "12 months",
        "methodology": "m",
    }
    mock_struct.side_effect = [clash, pt]

    events = list(agents.run_debate("TSLA", notes="heads up: earnings next week"))
    final = [e for e in events if e["type"] == "debate_complete"][0]["debate"]

    assert final["ticker"] == "TSLA"
    assert final["notes"] == "heads up: earnings next week"
    assert final["researcher"] == "stub"
    assert set(final["bull"].keys()) == {
        "fundamentals", "growth", "macro", "moat", "capital", "technicals"
    }
    assert set(final["bear"].keys()) == {
        "risk", "valuation", "headwinds", "disruption", "accounting", "technicals"
    }
    assert final["clash"] == clash
    assert final["priceTarget"] == pt
    # timestamp is ISO-8601 string
    assert "T" in final["timestamp"]


@patch("agents.run_structured_agent")
@patch("agents.run_agent")
def test_run_debate_survives_researcher_failure(mock_text, mock_struct):
    def flaky_text(system, user, **kw):
        if "research" in system.lower():
            raise agents.AgentError("WebSearch unavailable")
        return "analyst stub"
    mock_text.side_effect = flaky_text
    mock_struct.side_effect = [
        {"clashPoints": [], "winner": "BULL", "verdict": 7, "summary": "ok"},
        {
            "currentPrice": 0,
            "bullCase": {"price": 10, "probability": 0.3, "reasoning": "r"},
            "baseCase": {"price": 5, "probability": 0.5, "reasoning": "r"},
            "bearCase": {"price": 1, "probability": 0.2, "reasoning": "r"},
            "expectedValue": 4.7,
            "timeHorizon": "12 months",
            "methodology": "m",
        },
    ]

    events = list(agents.run_debate("NVDA", notes=""))
    final = [e for e in events if e["type"] == "debate_complete"][0]["debate"]
    assert final["researcher"].startswith("n/a")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_agents.py -v`
Expected: 4 new tests fail with `AttributeError: module 'agents' has no attribute 'run_debate'`.

- [ ] **Step 3: Implement the orchestrator**

Append to `agents.py`:

```python
from datetime import datetime

import prompts as _prompts


# Ordered pipeline. Each entry: (event_key, label, kind, bucket_path)
# kind in {"research", "analyst_bull", "analyst_bear", "judge", "price_target"}
_PIPELINE: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("researcher",         "🔎 Researching…",            "research",     ("researcher",)),
    ("bull_fundamentals",  "📊 Bull Fundamentals…",      "analyst_bull", ("bull", "fundamentals")),
    ("bull_growth",        "🚀 Bull Growth Catalysts…",  "analyst_bull", ("bull", "growth")),
    ("bull_macro",         "🌍 Bull Macro Tailwinds…",   "analyst_bull", ("bull", "macro")),
    ("bull_moat",          "🏰 Bull Moat & Pricing…",    "analyst_bull", ("bull", "moat")),
    ("bull_capital",       "💎 Bull Capital Allocation…", "analyst_bull", ("bull", "capital")),
    ("bull_technicals",    "📈 Bull Technicals…",         "analyst_bull", ("bull", "technicals")),
    ("bear_risk",          "⚠️ Bear Risk Factors…",       "analyst_bear", ("bear", "risk")),
    ("bear_valuation",     "💰 Bear Valuation…",          "analyst_bear", ("bear", "valuation")),
    ("bear_headwinds",     "🌪️ Bear Macro Headwinds…",    "analyst_bear", ("bear", "headwinds")),
    ("bear_disruption",    "🎯 Bear Disruption…",         "analyst_bear", ("bear", "disruption")),
    ("bear_accounting",    "🚩 Bear Accounting & Sentiment…", "analyst_bear", ("bear", "accounting")),
    ("bear_technicals",    "📉 Bear Technicals…",         "analyst_bear", ("bear", "technicals")),
    ("judge",              "⚖️ Judging…",                 "judge",        ("clash",)),
    ("price_target",       "🎯 Building price target…",    "price_target", ("priceTarget",)),
]


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_agents.py -v`
Expected: all tests pass (15 total).

- [ ] **Step 5: Commit**

```bash
git add agents.py tests/test_agents.py
git commit -m "feat: run_debate orchestrator — 15-agent sequential pipeline"
```

---

## Task 6: storage.py — persist debates as JSON

**Files:**
- Create: `storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_storage.py`:

```python
import json
import os
from datetime import datetime

import storage


def _sample_debate(ticker: str = "AAPL", ts: str = "2026-04-23T14:32:00") -> dict:
    return {
        "ticker": ticker,
        "timestamp": ts,
        "notes": "",
        "researcher": "r",
        "bull": {"fundamentals": "f"},
        "bear": {"risk": "r"},
        "clash": {"winner": "BULL", "verdict": 7, "summary": "s", "clashPoints": []},
        "priceTarget": {
            "currentPrice": 100.0,
            "bullCase": {"price": 120, "probability": 0.3, "reasoning": "r"},
            "baseCase": {"price": 110, "probability": 0.5, "reasoning": "r"},
            "bearCase": {"price": 90,  "probability": 0.2, "reasoning": "r"},
            "expectedValue": 109.0,
            "timeHorizon": "12 months",
            "methodology": "m",
        },
    }


def test_save_and_load_roundtrip(tmp_path):
    debate = _sample_debate()
    path = storage.save_debate(debate, base_dir=tmp_path)
    assert path.exists()
    loaded = storage.load_debate(path)
    assert loaded == debate


def test_filename_shape(tmp_path):
    debate = _sample_debate(ticker="TSLA", ts="2026-04-23T14:32:00")
    path = storage.save_debate(debate, base_dir=tmp_path)
    assert path.name == "TSLA-20260423-1432.json"


def test_list_debates_returns_newest_first(tmp_path):
    storage.save_debate(_sample_debate("AAPL", "2026-04-20T10:00:00"), base_dir=tmp_path)
    storage.save_debate(_sample_debate("TSLA", "2026-04-23T14:32:00"), base_dir=tmp_path)
    storage.save_debate(_sample_debate("NVDA", "2026-04-22T09:00:00"), base_dir=tmp_path)

    entries = storage.list_debates(base_dir=tmp_path)
    tickers = [e["ticker"] for e in entries]
    assert tickers == ["TSLA", "NVDA", "AAPL"]
    assert all("path" in e and "timestamp" in e and "verdict" in e for e in entries)


def test_list_debates_includes_summary_fields(tmp_path):
    d = _sample_debate()
    storage.save_debate(d, base_dir=tmp_path)
    [entry] = storage.list_debates(base_dir=tmp_path)
    assert entry["winner"] == "BULL"
    assert entry["verdict"] == 7
    assert entry["expectedValue"] == 109.0


def test_clear_debates_removes_all_files(tmp_path):
    storage.save_debate(_sample_debate("A"), base_dir=tmp_path)
    storage.save_debate(_sample_debate("B", "2026-04-23T15:00:00"), base_dir=tmp_path)
    storage.clear_debates(base_dir=tmp_path)
    assert storage.list_debates(base_dir=tmp_path) == []


def test_list_debates_skips_non_json(tmp_path):
    (tmp_path / "note.txt").write_text("ignore me")
    storage.save_debate(_sample_debate(), base_dir=tmp_path)
    entries = storage.list_debates(base_dir=tmp_path)
    assert len(entries) == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_storage.py -v`
Expected: `ModuleNotFoundError: No module named 'storage'`.

- [ ] **Step 3: Implement storage.py**

Create `storage.py`:

```python
"""JSON-file persistence for debate results."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


DEFAULT_DIR = Path(__file__).resolve().parent / "debates"


def _resolve_dir(base_dir: Path | None) -> Path:
    path = Path(base_dir) if base_dir else DEFAULT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _filename_for(debate: dict) -> str:
    ticker = debate["ticker"].upper()
    ts = datetime.fromisoformat(debate["timestamp"])
    return f"{ticker}-{ts.strftime('%Y%m%d-%H%M')}.json"


def save_debate(debate: dict, *, base_dir: Path | None = None) -> Path:
    """Write debate dict as JSON, return the file path."""
    target_dir = _resolve_dir(base_dir)
    path = target_dir / _filename_for(debate)
    path.write_text(json.dumps(debate, indent=2))
    return path


def load_debate(path: Path) -> dict:
    """Load a single debate JSON file."""
    return json.loads(Path(path).read_text())


def list_debates(*, base_dir: Path | None = None) -> list[dict]:
    """Return debate summary entries sorted newest-first.

    Each entry: {path, ticker, timestamp, winner, verdict, expectedValue}.
    """
    target_dir = _resolve_dir(base_dir)
    entries: list[dict] = []
    for p in target_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        entries.append({
            "path": p,
            "ticker": d.get("ticker", "?"),
            "timestamp": d.get("timestamp", ""),
            "winner": d.get("clash", {}).get("winner", "?"),
            "verdict": d.get("clash", {}).get("verdict", 0),
            "expectedValue": d.get("priceTarget", {}).get("expectedValue"),
        })
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


def clear_debates(*, base_dir: Path | None = None) -> int:
    """Delete every .json file in the debates directory. Returns count deleted."""
    target_dir = _resolve_dir(base_dir)
    count = 0
    for p in target_dir.glob("*.json"):
        p.unlink()
        count += 1
    return count
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_storage.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "feat: filesystem persistence for debate JSON"
```

---

## Task 7: app.py — form UI skeleton

**Files:**
- Create: `app.py`

No unit tests — Streamlit apps are verified manually. We smoke-test the import and then launch the dev server.

- [ ] **Step 1: Create the minimal form**

Create `app.py`:

```python
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
```

- [ ] **Step 2: Smoke-test the import**

Run: `python -c "import app"`
Expected: no exceptions (Streamlit may print a deprecation warning about `set_page_config` during import; that's fine).

- [ ] **Step 3: Launch and confirm the form renders**

Run: `streamlit run app.py`
Expected: the browser opens at `http://localhost:8501` and shows the title + ticker form.
Type `AAPL` → click Debate → you see the placeholder "Running debate for AAPL…" message.
Stop Streamlit with Ctrl-C.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: app.py form UI + startup check"
```

---

## Task 8: app.py — running state (wire up run_debate)

**Files:**
- Modify: `app.py`

Background: Streamlit doesn't natively support long-running generators inside a rerun cycle. Simplest pattern: once the form is submitted, the "running" rerun consumes the generator synchronously using `st.status()` as a live progress container, then saves the debate and transitions to "done". A single rerun does the work.

- [ ] **Step 1: Replace the running-state branch**

Find in `app.py`:

```python
    elif st.session_state.phase == "running":
        st.info(f"Running debate for {st.session_state._pending_ticker}… (wired up in the next task)")
```

Replace with:

```python
    elif st.session_state.phase == "running":
        render_running()
```

- [ ] **Step 2: Add `render_running`**

Insert before `def main()`:

```python
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
```

- [ ] **Step 3: Show errors on the form page**

Find inside `main()`:

```python
    if st.session_state.phase == "idle":
        render_form()
```

Replace with:

```python
    if st.session_state.phase == "idle":
        if st.session_state.error:
            st.error(st.session_state.error)
            st.session_state.error = None
        render_form()
```

- [ ] **Step 4: Manual test with a lightweight ticker**

Run: `streamlit run app.py`
Use a ticker whose debate you're willing to wait 4-7 minutes for (e.g. `AAPL`).
Expected:
- Progress bar climbs 0 → 15.
- Phase label updates after each of the 15 agents.
- Live expander shows a snippet of each agent's output.
- When complete, the app flips to "done" phase (still a placeholder result panel).
- A JSON file appears in `debates/`.

If the run errors, read the message and fix the prompt/schema; commit any tweaks separately.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: wire app.py to run_debate generator with live progress"
```

---

## Task 9: app.py — result panel

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace the done-state branch**

Find in `main()`:

```python
    else:
        st.info("Results panel wired up in the next task.")
```

Replace with:

```python
    else:
        render_result(st.session_state.debate)
```

- [ ] **Step 2: Add `render_result` and its helpers**

Insert before `def main()`:

```python
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
```

- [ ] **Step 3: Manual test**

Launch: `streamlit run app.py`
Run a full debate (or use an existing JSON from `debates/` if the generator is still a bit flaky).
Expected:
- Verdict banner renders colored (green for BULL, red for BEAR) with the score.
- Three metrics show current / expected / range; upside percentage appears under "Expected".
- Price target methodology expander shows all three scenarios with probabilities.
- 2-3 clash point expanders render with bull/bear/reasoning lines.
- Two columns of 6 expanders each.
- Researcher findings expander at the bottom.
- "New debate" button resets to the form.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: result panel — verdict, price target, clash, agents"
```

---

## Task 10: app.py — sidebar history

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add `render_sidebar` and its helper**

Insert before `def main()`:

```python
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
```

- [ ] **Step 2: Call the sidebar from `main`**

Find the start of `main`:

```python
def main() -> None:
    _startup_check()
    _init_session_state()
```

Insert `render_sidebar()` right after `_init_session_state()`:

```python
def main() -> None:
    _startup_check()
    _init_session_state()
    render_sidebar()
```

- [ ] **Step 3: Manual test**

Launch: `streamlit run app.py`
Expected:
- Sidebar shows past debates (if any exist in `debates/`).
- Clicking a past debate loads its result panel.
- "Clear history" button shows confirmation, then wipes `debates/`.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: sidebar — past debates list + clear history"
```

---

## Task 11: error-handling polish

**Files:**
- Modify: `agents.py` (add rate-limit retry)
- Modify: `app.py` (retry button on error)

- [ ] **Step 1: Add rate-limit retry in run_agent**

In `agents.py`, find the `run_agent` function's subprocess call:

```python
    with tempfile.TemporaryDirectory(prefix="bba-") as clean_cwd:
        proc = subprocess.run(
            argv,
            cwd=clean_cwd,
            capture_output=True,
            text=True,
            timeout=AGENT_TIMEOUT_SECONDS,
        )
```

Replace with a retry-aware helper:

```python
    proc = _run_with_retry(argv)
```

Then add this helper just above `run_agent` (after the `AgentError` class):

```python
import time


def _looks_like_rate_limit(stderr: str) -> bool:
    s = stderr.lower()
    return "429" in s or "rate limit" in s or "rate_limit" in s


def _run_with_retry(argv: list[str], *, attempts: int = 2, wait_s: int = 30):
    last_err = ""
    for attempt in range(attempts):
        with tempfile.TemporaryDirectory(prefix="bba-") as clean_cwd:
            proc = subprocess.run(
                argv,
                cwd=clean_cwd,
                capture_output=True,
                text=True,
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        if proc.returncode == 0:
            return proc
        last_err = proc.stderr
        if not _looks_like_rate_limit(proc.stderr):
            return proc
        if attempt + 1 < attempts:
            time.sleep(wait_s)
    # All attempts failed — return the final proc so caller raises AgentError
    return proc
```

Do the same swap inside `run_structured_agent` — replace its `with tempfile.TemporaryDirectory(...)` block with `proc = _run_with_retry(argv)`.

- [ ] **Step 2: Add a retry test**

Append to `tests/test_agents.py`:

```python
@patch("agents.time.sleep", return_value=None)
@patch("agents.subprocess.run")
def test_run_agent_retries_once_on_rate_limit(mock_run, _sleep):
    first = MagicMock(returncode=1, stdout="", stderr="HTTP 429 rate limit exceeded")
    second = _fake_proc("recovered")
    mock_run.side_effect = [first, second]

    assert agents.run_agent("sys", "user") == "recovered"
    assert mock_run.call_count == 2
```

Run: `python -m pytest tests/test_agents.py -v`
Expected: all tests pass including the new retry test.

- [ ] **Step 3: Add a retry button when a debate fails mid-flight**

In `app.py`, inside `render_running`, find the `except agents.AgentError` block:

```python
        except agents.AgentError as e:
            st.session_state.error = str(e)
            st.session_state.phase = "idle"
            status.update(label=f"Failed: {e}", state="error")
```

Replace with:

```python
        except agents.AgentError as e:
            st.session_state.error = (
                f"{e}\n\nTip: the ticker and your notes are still filled in on the form — "
                f"just click Debate again to retry."
            )
            st.session_state.phase = "idle"
            status.update(label=f"Failed: {e}", state="error")
```

And inside `render_form()`, set the form defaults from session state:

```python
            ticker = st.text_input(
                "Ticker",
                value=st.session_state.get("_pending_ticker", ""),
                placeholder="AAPL", max_chars=10,
            ).strip().upper()
```

```python
            notes = st.text_area(
                "Optional context (breaking news, earnings, etc.)",
                value=st.session_state.get("_pending_notes", ""),
                placeholder="Optional — paste any context you want every agent to see.",
                height=80,
            )
```

- [ ] **Step 4: Commit**

```bash
git add agents.py app.py tests/test_agents.py
git commit -m "feat: rate-limit retry + preserve ticker on failure"
```

---

## Task 12: smoke test + README polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full pipeline for real**

Launch: `streamlit run app.py`
Run a debate for `AAPL`. Time it end-to-end. Expected: ~4-7 minutes, 15 progress bar steps, final panel renders with numbers that are plausible (current price within 10% of today's actual price).

- [ ] **Step 2: Run a second ticker**

Run a debate for a smaller / less-covered ticker of your choice. Verify the UI still renders cleanly when WebSearch finds less information.

- [ ] **Step 3: Verify persistence + sidebar**

Reload the browser at `localhost:8501`. Both past debates should appear in the sidebar. Click each — their result panels should render identically to how they looked right after completion.

- [ ] **Step 4: Flesh out README**

Replace `README.md` with:

```markdown
# Bull vs Bear Arena

Local Streamlit app that runs a 15-agent stock debate using the Claude Code CLI.
No API key — every agent call is a `claude -p` subprocess against your Claude
Code subscription.

You type a ticker, hit **Debate**, and in ~4-7 minutes you get:

- A researcher brief with live WebSearch results
- Twelve specialist arguments (6 bull, 6 bear)
- A judge's clash points + BULL/BEAR verdict + 1-10 conviction score
- A quantitative price target with bull / base / bear scenarios and expected value

Results render as expandable panels and persist as JSON under `debates/`.

## Requirements

- Python 3.11+
- `claude` CLI 2.1+ installed and authenticated (run `claude` once to sign in)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Project layout

```
app.py          # Streamlit UI
agents.py       # Pipeline orchestrator + subprocess wrapper
prompts.py      # 15 agent personas + 2 JSON schemas
storage.py      # Save/load debate JSON
tests/          # pytest unit tests
docs/
  specs/        # design doc
  plans/        # implementation plan
debates/        # saved debate JSON (gitignored)
```

## Running tests

```bash
python -m pytest tests/ -v
```

## Design

See [`docs/specs/2026-04-23-bull-bear-arena-design.md`](docs/specs/2026-04-23-bull-bear-arena-design.md)
and [`docs/plans/2026-04-23-bull-bear-arena.md`](docs/plans/2026-04-23-bull-bear-arena.md).
```

- [ ] **Step 5: Final commit**

```bash
git add README.md
git commit -m "docs: flesh out README after smoke-test pass"
```

- [ ] **Step 6: Confirm test suite is green**

Run: `python -m pytest tests/ -v`
Expected: all tests pass.
