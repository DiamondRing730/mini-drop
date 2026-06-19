"""Analyzer configuration from MINIDROP_* env vars."""
import os


class Config:
    def __init__(self) -> None:
        self.server_url = os.environ.get("MINIDROP_SERVER_URL", "http://server:8000").rstrip("/")
        self.artifacts_dir = os.environ.get("MINIDROP_ARTIFACTS_DIR", "/data/artifacts")
        self.poll_interval_sec = float(os.environ.get("MINIDROP_ANALYZER_POLL_INTERVAL", "2"))
        self.topn = int(os.environ.get("MINIDROP_TOPN", "15"))
