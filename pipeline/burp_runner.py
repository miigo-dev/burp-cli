"""Invokes burp-cli --job <path> as a subprocess, captures its output to a
log file, and extracts the export directory it printed.

Prefers the compiled binary (BURP_CLI_PATH). If that binary is missing, or
the OS refuses to launch it at all (observed in locked-down environments
where an Application Control / AppLocker policy blocks direct exe
execution), falls back to `go run .` against the source tree
(BURP_CLI_SOURCE_DIR) instead -- same behavior, no binary required.

A launch failure (missing binary, OS-blocked execution) triggers the
fallback; a timeout does not -- a timeout means the process *did* launch and
was still running when the safety net tripped, which is a real outcome to
report, not a reason to retry via a different invocation method (that would
just start a second, duplicate scan).

No artificial short timeout: a real deep scan observed against a live Burp
Suite Pro instance ran 30+ minutes and wasn't finished when manually
stopped. BURP_SUBPROCESS_TIMEOUT_MINUTES is a generous dead-process safety
net, not a real cap -- blocking the Task-Scheduler-triggered process for the
full scan duration is expected; the Sheet-based row claim (not process
lifetime) is what prevents a second firing from double-processing a row.
"""

import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import NamedTuple, Optional

import config

logger = logging.getLogger(__name__)

EXPORT_DIR_PATTERN = re.compile(r"Created export directory: (\S+)")


class BurpRunResult(NamedTuple):
    success: bool
    exit_code: int
    export_dir: str
    log_path: Path


class _LaunchError(Exception):
    """The process could not be started at all (missing binary, OS-blocked
    execution). Distinct from the process launching and then timing out."""


def _launch(argv: list, cwd: Optional[str], timeout_seconds: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout_seconds, cwd=cwd)
    except (FileNotFoundError, OSError) as exc:
        raise _LaunchError(str(exc)) from exc


def run_job(job_path: Path, row_number: int) -> BurpRunResult:
    job_args = ["--job", str(job_path), "-t", config.BURP_TARGET_HOST, "-p", config.BURP_TARGET_PORT]
    timeout_seconds = config.BURP_SUBPROCESS_TIMEOUT_MINUTES * 60
    log_path = config.LOG_DIR / f"row_{row_number}_{int(time.time())}.log"

    exe_path = Path(config.BURP_CLI_PATH)
    completed = None
    timed_out = False
    launch_errors = []

    if exe_path.is_file():
        argv = [str(exe_path)] + job_args
        logger.info("Running: %s", " ".join(argv))
        try:
            completed = _launch(argv, None, timeout_seconds)
        except _LaunchError as exc:
            launch_errors.append(f"binary ({exe_path}): {exc}")
            logger.warning("Compiled binary launch failed (%s); falling back to `go run .`", exc)
        except subprocess.TimeoutExpired:
            timed_out = True
    else:
        launch_errors.append(f"binary: not found at {exe_path}")
        logger.warning("burp-cli binary not found at %s; falling back to `go run .`", exe_path)

    if completed is None and not timed_out:
        go_exe = shutil.which("go")
        if go_exe is None:
            launch_errors.append("go run: `go` not found on PATH")
            msg = "; ".join(launch_errors)
            log_path.write_text(msg, encoding="utf-8")
            logger.error("Cannot invoke burp-cli by any method for row %d: %s", row_number, msg)
            return BurpRunResult(success=False, exit_code=-1, export_dir="", log_path=log_path)

        argv = [go_exe, "run", "."] + job_args
        logger.info("Running (source fallback): %s (cwd=%s)", " ".join(argv), config.BURP_CLI_SOURCE_DIR)
        try:
            completed = _launch(argv, str(config.BURP_CLI_SOURCE_DIR), timeout_seconds)
        except _LaunchError as exc:
            launch_errors.append(f"go run: {exc}")
            msg = "; ".join(launch_errors)
            log_path.write_text(msg, encoding="utf-8")
            logger.error("Both invocation methods failed for row %d: %s", row_number, msg)
            return BurpRunResult(success=False, exit_code=-1, export_dir="", log_path=log_path)
        except subprocess.TimeoutExpired:
            timed_out = True

    if timed_out:
        log_path.write_text(
            f"burp-cli exceeded the {config.BURP_SUBPROCESS_TIMEOUT_MINUTES}-minute safety-net timeout\n",
            encoding="utf-8",
        )
        logger.error(
            "burp-cli exceeded the %d-minute safety-net timeout for row %d",
            config.BURP_SUBPROCESS_TIMEOUT_MINUTES, row_number,
        )
        return BurpRunResult(success=False, exit_code=-1, export_dir="", log_path=log_path)

    combined = completed.stdout + "\n" + completed.stderr
    log_path.write_text(combined, encoding="utf-8")

    export_dir = ""
    match = EXPORT_DIR_PATTERN.search(combined)
    if match:
        export_dir = match.group(1)

    success = completed.returncode == 0
    if not success:
        logger.error("burp-cli exited %d for row %d; see %s", completed.returncode, row_number, log_path)

    return BurpRunResult(success=success, exit_code=completed.returncode, export_dir=export_dir, log_path=log_path)
