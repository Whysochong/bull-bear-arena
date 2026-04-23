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
