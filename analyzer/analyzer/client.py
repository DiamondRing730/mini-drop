"""HTTP client for the analyzer's internal endpoints."""
import requests


class AnalyzerClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()

    def next_job(self) -> dict | None:
        r = self.session.get(
            f"{self.base_url}/api/v1/internal/analysis/next", timeout=self.timeout
        )
        r.raise_for_status()
        return r.json().get("task")

    def report(self, tid: str, success: bool, files: dict | None = None, error: str = "") -> dict:
        r = self.session.post(
            f"{self.base_url}/api/v1/internal/analysis/{tid}/result",
            json={"success": success, "analysis_files": files or {}, "error": error},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()
