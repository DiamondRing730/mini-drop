"""Collector interface + subprocess helpers with hard process-group timeouts.

Collectors fork external tools (perf / py-spy). We always launch them in their own
session/process-group (start_new_session=True) so that on timeout we can kill the WHOLE
group with killpg — otherwise a perf that spawned children would leave orphans behind.
"""
import logging
import os
import signal
import subprocess

logger = logging.getLogger("minidrop.agent.collector")


class CollectorError(Exception):
    """A collection failed (tool missing, bad PID, non-zero exit, no output...)."""


def _tail(text: str, n: int = 400) -> str:
    text = (text or "").strip()
    return text[-n:]


def _terminate_group(proc: subprocess.Popen, grace: int) -> None:
    """SIGTERM the process group, then SIGKILL after `grace` seconds if still alive."""
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run(cmd: list[str], timeout: int, stdout_path: str | None = None, grace: int = 5):
    """Run `cmd` with a timeout. Returns (returncode, stdout_text, stderr_text).

    If stdout_path is given, stdout is streamed to that file and the returned stdout
    text is empty (used for large outputs like `perf script`).
    """
    logger.info("exec: %s", " ".join(cmd))
    stdout_target = open(stdout_path, "wb") if stdout_path else subprocess.PIPE
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=stdout_target,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=False,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_group(proc, grace)
            out, err = proc.communicate()
        rc = proc.returncode
        out_text = "" if stdout_path else (out.decode(errors="replace") if out else "")
        err_text = err.decode(errors="replace") if err else ""
        return rc, out_text, err_text
    finally:
        if stdout_path:
            stdout_target.close()


class Collector:
    """Base class. A collector turns a task into one or more artifact files on disk.

    collect() returns a {logical_name: filename} mapping (filenames relative to out_dir,
    which lives on the shared volume the server/analyzer also see).
    """

    name = "base"

    def collect(self, task: dict, out_dir: str) -> dict:
        raise NotImplementedError
