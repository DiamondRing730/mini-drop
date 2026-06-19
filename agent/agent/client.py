"""Thin HTTP client to the Mini-Drop server."""
import requests


class ServerClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()

    def heartbeat(self, payload: dict) -> dict:
        r = self.session.post(
            f"{self.base_url}/api/v1/agent/heartbeat", json=payload, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def report_status(self, tid: str, status: str, reason: str = "") -> dict:
        r = self.session.post(
            f"{self.base_url}/api/v1/agent/tasks/{tid}/status",
            json={"status": status, "reason": reason},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def report_result(self, tid: str, success: bool, error: str = "", files: dict | None = None) -> dict:
        r = self.session.post(
            f"{self.base_url}/api/v1/agent/tasks/{tid}/result",
            json={"success": success, "error_message": error, "result_files": files or {}},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()
