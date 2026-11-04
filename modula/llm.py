"""Calls Claude through the Claude Code command line, so no API key is needed.
The computer running this must be signed in once with: claude auth login
"""
import json
import shutil
import subprocess

MODEL = "claude-haiku-5-5"
TIMEOUT_SECONDS = 90


class LLMError(Exception):
    pass


def is_available():
    """True when the Claude CLI is installed and signed in."""
    path = shutil.which("claude")
    if not path:
        return False
    try:
        done = subprocess.run([path, "auth", "status"], capture_output=True, text=True, timeout=20)
        return bool(json.loads(done.stdout).get("loggedIn"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def complete(prompt):
    """Sends one prompt and returns the reply text."""
    path = shutil.which("claude")
    if not path:
        raise LLMError("The Claude CLI is not installed.")
    command = [path, "-p", "--model", MODEL, "--output-format", "text", "--no-session-persistence",
               "--tools", "", "--strict-mcp-config",
               "--system-prompt", "Follow the user message exactly. Output only what it asks for."]
    try:
        done = subprocess.run(command, input=prompt, capture_output=True, encoding="utf-8",
                              timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        raise LLMError(str(error)) from error
    if done.returncode != 0 or not done.stdout.strip():
        raise LLMError((done.stdout or done.stderr or "Claude returned nothing.").strip()[:200])
    return done.stdout
