import json
import os
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
    cwd = str(kwargs["cwd"])
    home = os.path.expanduser("~")
    # Real invariant: cwd is outside $HOME so claude won't walk up into ~/CLAUDE.md
    assert not cwd.startswith(home), f"cwd {cwd} is inside HOME — CLAUDE.md ancestor walk will pick it up"


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
