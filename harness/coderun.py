"""Run model-generated code in a SUBPROCESS with a timeout. Never exec() in-process.

`run_python(code, timeout)` writes `code` to a temp file and runs it with the
current interpreter as a separate process, capturing stdout/stderr and killing
the whole process group on timeout.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time

SCRATCH = os.environ.get(
    "MATHEVALS_SCRATCH",
    "/private/tmp/claude-501/-Users-khushambansal-Research-MathEvals/"
    "352e84dc-e33f-4969-9909-612b2e65b014/scratchpad",
)


def run_python(code: str, timeout: float = 12.0, extra_env: dict | None = None) -> dict:
    """Execute `code` in a fresh subprocess.

    Returns dict: stdout, stderr, returncode, timed_out (bool), seconds (float).
    """
    os.makedirs(SCRATCH, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".py", prefix="gen_", dir=SCRATCH)
    os.close(fd)
    with open(path, "w") as fh:
        fh.write(code)

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONHASHSEED": "0",
        # no OPENAI_API_KEY etc. leaked into generated code
    }
    if extra_env:
        env.update(extra_env)

    start = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            [sys.executable, "-I", path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=SCRATCH,
            start_new_session=True,  # own process group -> clean kill on timeout
        )
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = e.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        stderr = (e.stderr or "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        stderr += f"\n[timed out after {timeout}s]"
        rc = -signal.SIGKILL
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    return {
        "stdout": stdout,
        "stderr": stderr,
        "returncode": rc,
        "timed_out": timed_out,
        "seconds": round(time.time() - start, 3),
    }
