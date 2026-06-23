import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from config import HIGGSFIELD_CLI_TIMEOUT

logger = logging.getLogger(__name__)

_HIGGSFIELD_FALLBACK = (
    r"C:\Users\HR 1\AppData\Roaming\fnm\node-versions\v20.20.2\installation\higgsfield.cmd"
)

def _resolve_higgsfield() -> str:
    """Returns the higgsfield executable path, checking PATH then the known fnm install location."""
    found = shutil.which("higgsfield")
    if found:
        return found
    if Path(_HIGGSFIELD_FALLBACK).exists():
        return _HIGGSFIELD_FALLBACK
    raise RuntimeError(
        "higgsfield CLI not found. Install with: npm install -g @higgsfield/cli"
    )


_CMD_UNSAFE = str.maketrans({
    "&": "and",
    "|": ",",
    "<": "",
    ">": "",
    "^": "",
})


def _sanitize_prompt(arg: str) -> str:
    """Replace cmd.exe shell operators in prompt text so .cmd wrappers don't split on them."""
    return arg.translate(_CMD_UNSAFE)


def _run_cmd(cmd: list[str], timeout: int) -> str:
    """Runs a command, returns stdout. Raises RuntimeError on failure."""
    # Sanitize every non-flag argument (prompt text) — Windows .cmd files re-expand %*
    # which means & | < > can break the command even inside double-quoted args.
    safe_cmd = []
    for arg in cmd:
        # Only sanitize value args (not flags like --prompt, --aspect_ratio, etc.)
        if arg.startswith("--") or arg in ("generate", "create", "wait", "get", "model"):
            safe_cmd.append(arg)
        else:
            safe_cmd.append(_sanitize_prompt(arg))
    try:
        result = subprocess.run(safe_cmd, capture_output=True, text=True, timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Higgsfield CLI timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError(f"higgsfield CLI not found at {cmd[0]}. Install: npm install -g @higgsfield/cli")
    if result.returncode != 0:
        raise RuntimeError(f"Higgsfield CLI error (exit {result.returncode}):\n{result.stderr.strip()}")
    return result.stdout.strip()


def _parse_json(raw: str) -> dict:
    """Parse JSON from CLI output — handles multi-line output where UUID precedes JSON."""
    if not raw:
        raise RuntimeError("Higgsfield CLI returned empty output")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise RuntimeError(f"Higgsfield CLI returned non-JSON output: {raw[:200]}")


def run_higgsfield(args: list[str], timeout: Optional[int] = None) -> dict:
    """
    Submits a Higgsfield job and waits for completion via `generate wait <job_id>`.

    Step 1 — `generate create ...` → returns job ID (plain UUID or JSON list)
    Step 2 — `generate wait <job_id>` → blocks until done, returns result JSON
    """
    exe = _resolve_higgsfield()
    t = timeout or HIGGSFIELD_CLI_TIMEOUT

    # ── Step 1: Submit job ────────────────────────────────────────────────────
    submit_cmd = [exe] + args + ["--json"]
    logger.info(f"Higgsfield CLI: {' '.join(submit_cmd[1:])}")
    raw_submit = _run_cmd(submit_cmd, timeout=60)

    # Extract job ID — may be plain UUID string or JSON array ["uuid"]
    job_id = None
    try:
        parsed = json.loads(raw_submit)
        if isinstance(parsed, list) and parsed:
            job_id = str(parsed[0])
        elif isinstance(parsed, dict):
            job_id = parsed.get("id") or parsed.get("job_id")
    except json.JSONDecodeError:
        job_id = raw_submit.strip().splitlines()[0].strip()

    if not job_id:
        raise RuntimeError(f"Could not extract job ID from submit response: {raw_submit[:200]}")

    logger.info(f"Job submitted: {job_id} — waiting for completion...")

    # ── Step 2: Wait for result ───────────────────────────────────────────────
    wait_cmd = [exe, "generate", "wait", job_id, "--timeout", "20m", "--interval", "10s", "--json"]
    raw_result = _run_cmd(wait_cmd, timeout=t)

    return _parse_json(raw_result)
