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
def test_run_structured_agent_embeds_schema_in_system_prompt(mock_run):
    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    mock_run.return_value = _fake_proc('{"x": "y"}')
    agents.run_structured_agent("base system", "user", schema=schema)

    argv = mock_run.call_args[0][0]
    # Schema is appended to --system-prompt rather than passed as a CLI flag
    assert "--json-schema" not in argv
    system_value = argv[argv.index("--system-prompt") + 1]
    assert "base system" in system_value
    assert '"type": "object"' in system_value
    assert '"required"' in system_value


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


@patch("agents.subprocess.run")
def test_run_agent_raises_agent_error_on_timeout(mock_run):
    import subprocess as _sp
    mock_run.side_effect = _sp.TimeoutExpired(cmd="claude", timeout=300)
    try:
        agents.run_agent("sys", "user")
    except agents.AgentError as e:
        assert "timed out" in str(e).lower()
    else:
        raise AssertionError("expected AgentError on timeout")


@patch("agents.time.sleep", return_value=None)
@patch("agents.subprocess.run")
def test_run_agent_does_not_retry_on_non_rate_limit_failure(mock_run, _sleep):
    fail = MagicMock(returncode=1, stdout="", stderr="Error: unknown flag --foo")
    mock_run.return_value = fail
    try:
        agents.run_agent("sys", "user")
    except agents.AgentError:
        pass
    else:
        raise AssertionError("expected AgentError")
    # Must have been called exactly once — no retry for non-rate-limit failures
    assert mock_run.call_count == 1


AGENT_SEQUENCE = [
    "researcher", "fact_checker",
    "bull_fundamentals", "bull_growth", "bull_macro",
    "bull_moat", "bull_capital", "bull_technicals",
    "bear_risk", "bear_valuation", "bear_headwinds",
    "bear_disruption", "bear_accounting", "bear_technicals",
    "head_bull", "head_bear",
    "price_target", "judge",
]
SPECIALIST_KEYS = set(AGENT_SEQUENCE[2:14])
HEAD_KEYS = {"head_bull", "head_bear"}
TOTAL_AGENTS = 18

_PT_MOCK = {
    "currentPrice": 100.0,
    "bullCase": {"price": 120, "probability": 0.3, "reasoning": "r1"},
    "baseCase": {"price": 110, "probability": 0.5, "reasoning": "r2"},
    "bearCase": {"price": 90,  "probability": 0.2, "reasoning": "r3"},
    "expectedValue": 109.0,
    "timeHorizon": "12 months",
    "methodology": "multiples",
}
_CLASH_MOCK = {"clashPoints": [], "winner": "BULL", "verdict": 7, "summary": "ok"}


@patch("agents.run_structured_agent")
@patch("agents.run_agent")
def test_run_debate_emits_all_events(mock_text, mock_struct):
    mock_text.return_value = "stub analysis"
    # Price target runs BEFORE judge now, so the structured side_effects come
    # in that order too.
    mock_struct.side_effect = [_PT_MOCK, _CLASH_MOCK]

    events = list(agents.run_debate("AAPL", notes=""))
    starts = [e for e in events if e["type"] == "agent_start"]
    completes = [e for e in events if e["type"] == "agent_complete"]
    finals = [e for e in events if e["type"] == "debate_complete"]

    # agent_start events: in declaration order
    assert [e["key"] for e in starts] == AGENT_SEQUENCE
    # agent_complete order: researcher, fact_checker, then specialists (any
    # order), then heads (any order), then price_target, then judge.
    assert completes[0]["key"] == "researcher"
    assert completes[1]["key"] == "fact_checker"
    assert {e["key"] for e in completes[2:14]} == SPECIALIST_KEYS
    assert {e["key"] for e in completes[14:16]} == HEAD_KEYS
    assert completes[16]["key"] == "price_target"
    assert completes[17]["key"] == "judge"

    assert len(finals) == 1
    assert sorted(e["step"] for e in starts) == list(range(1, TOTAL_AGENTS + 1))
    assert all(e["total"] == TOTAL_AGENTS for e in starts)


@patch("agents.run_structured_agent")
@patch("agents.run_agent")
def test_run_debate_feeds_researcher_into_sub_agents(mock_text, mock_struct):
    def _mock(system, user, **kw):
        # The researcher is the only caller that passes tools=["WebSearch"].
        if kw.get("tools") == ["WebSearch"]:
            return "Current price: $180. RESEARCHER_OUTPUT"
        return f"PROMPT_CONTAINED:{int('RESEARCHER_OUTPUT' in user)}"
    mock_text.side_effect = _mock
    # Price target runs first, then judge.
    mock_struct.side_effect = [
        {
            "currentPrice": 180.0,
            "bullCase": {"price": 200, "probability": 0.3, "reasoning": "r"},
            "baseCase": {"price": 190, "probability": 0.5, "reasoning": "r"},
            "bearCase": {"price": 170, "probability": 0.2, "reasoning": "r"},
            "expectedValue": 189.0,
            "timeHorizon": "12 months",
            "methodology": "m",
        },
        {"clashPoints": [], "winner": "BULL", "verdict": 7, "summary": "ok"},
    ]

    events = list(agents.run_debate("AAPL", notes=""))
    completes = {e["key"]: e["text"] for e in events if e["type"] == "agent_complete"}
    # Every specialist (indices 2..13) must have seen the researcher context in
    # its user prompt. The researcher and fact_checker both call WebSearch so
    # they get the researcher-sentinel response back from the mock — that's
    # expected, they're the ones producing the context.
    for key in AGENT_SEQUENCE[2:14]:  # 12 specialists only
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
    # Price target runs first, then judge.
    mock_struct.side_effect = [pt, clash]

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
    assert final["headBull"] == "stub"
    assert final["headBear"] == "stub"
    assert final["clash"] == clash
    assert final["priceTarget"] == pt
    # timestamp is ISO-8601 string
    assert "T" in final["timestamp"]


@patch("agents.run_structured_agent")
@patch("agents.run_agent")
def test_run_debate_survives_researcher_failure(mock_text, mock_struct):
    def flaky_text(system, user, **kw):
        if kw.get("tools") == ["WebSearch"]:
            raise agents.AgentError("WebSearch unavailable")
        return "analyst stub"
    mock_text.side_effect = flaky_text
    # Price target runs first, then judge.
    mock_struct.side_effect = [
        {
            "currentPrice": 0,
            "bullCase": {"price": 10, "probability": 0.3, "reasoning": "r"},
            "baseCase": {"price": 5, "probability": 0.5, "reasoning": "r"},
            "bearCase": {"price": 1, "probability": 0.2, "reasoning": "r"},
            "expectedValue": 4.7,
            "timeHorizon": "12 months",
            "methodology": "m",
        },
        {"clashPoints": [], "winner": "BULL", "verdict": 7, "summary": "ok"},
    ]

    events = list(agents.run_debate("NVDA", notes=""))
    final = [e for e in events if e["type"] == "debate_complete"][0]["debate"]
    assert final["researcher"].startswith("n/a")


@patch("agents.time.sleep", return_value=None)
@patch("agents.subprocess.run")
def test_run_agent_retries_once_on_rate_limit(mock_run, _sleep):
    first = MagicMock(returncode=1, stdout="", stderr="HTTP 429 rate limit exceeded")
    second = _fake_proc("recovered")
    mock_run.side_effect = [first, second]

    assert agents.run_agent("sys", "user") == "recovered"
    assert mock_run.call_count == 2
