"""Agent configuration sourced from MINIDROP_* env vars, with a persisted agent id."""
import os
import socket
import uuid


def _detect_ip() -> str:
    """Best-effort primary IP (no traffic actually sent on the UDP socket)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _load_agent_id(path: str, env_val: str) -> str:
    """Stable agent id: explicit env wins, else read/create a file so restarts keep identity."""
    if env_val:
        return env_val
    if os.path.isfile(path):
        with open(path) as f:
            existing = f.read().strip()
        if existing:
            return existing
    agent_id = "agent-" + uuid.uuid4().hex[:12]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(agent_id)
    return agent_id


class Config:
    def __init__(self) -> None:
        self.server_url = os.environ.get("MINIDROP_SERVER_URL", "http://server:8000").rstrip("/")
        self.artifacts_dir = os.environ.get("MINIDROP_ARTIFACTS_DIR", "/data/artifacts")
        self.heartbeat_interval_sec = int(os.environ.get("MINIDROP_HEARTBEAT_INTERVAL", "5"))
        self.agent_version = os.environ.get("MINIDROP_AGENT_VERSION", "0.1.0")
        # Software event works under WSL2 where hardware PMU counters are unavailable.
        self.perf_event = os.environ.get("MINIDROP_PERF_EVENT", "cpu-clock")
        self.hostname = os.environ.get("MINIDROP_HOSTNAME", socket.gethostname())
        self.ip_addr = os.environ.get("MINIDROP_IP", _detect_ip())
        id_file = os.environ.get("MINIDROP_AGENT_ID_FILE", "/data/agent_id")
        self.agent_id = _load_agent_id(id_file, os.environ.get("MINIDROP_AGENT_ID", ""))
