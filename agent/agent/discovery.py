"""Read-only Docker target discovery through the local Unix socket.

The agent already runs in the host PID namespace for profiling. Docker's `top`
endpoint supplies the matching host PIDs, so users can choose a container/process
without opening a terminal. Discovery failures are intentionally non-fatal.
"""
import http.client
import json
import socket
import time
from urllib.parse import quote


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str):
        super().__init__("localhost", timeout=2)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _get(path: str, socket_path: str = "/var/run/docker.sock"):
    conn = _UnixHTTPConnection(socket_path)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        if response.status != 200:
            return None
        return json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()


def discover_containers(socket_path: str = "/var/run/docker.sock") -> list[dict]:
    try:
        containers = _get("/containers/json", socket_path) or []
        result = []
        for item in containers:
            cid = item.get("Id", "")
            top = _get(
                f"/containers/{cid}/top?ps_args={quote('-eo pid,ppid,comm,args', safe='')}",
                socket_path,
            ) or {}
            titles = [str(x).lower() for x in top.get("Titles", [])]
            processes = []
            for row in top.get("Processes", []):
                values = dict(zip(titles, row))
                try:
                    pid = int(values.get("pid", "0"))
                except ValueError:
                    continue
                if pid <= 0:
                    continue
                processes.append({
                    "pid": pid,
                    "ppid": int(values.get("ppid", "0") or 0),
                    "comm": values.get("comm", values.get("command", "")),
                    "args": values.get("args", values.get("cmd", "")),
                })
            result.append({
                "id": cid[:12],
                "name": (item.get("Names") or [cid[:12]])[0].lstrip("/"),
                "image": item.get("Image", ""),
                "processes": processes,
            })
        return result
    except (OSError, ValueError, http.client.HTTPException, json.JSONDecodeError):
        return []


class DiscoveryCache:
    def __init__(self, ttl_sec: float = 10.0):
        self.ttl_sec = ttl_sec
        self._at = 0.0
        self._value: list[dict] = []

    def get(self) -> list[dict]:
        now = time.monotonic()
        if now - self._at >= self.ttl_sec:
            self._value = discover_containers()
            self._at = now
        return self._value
