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
