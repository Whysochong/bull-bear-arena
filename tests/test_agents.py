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
