"""Small shared helpers."""
import uuid
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time. Used everywhere for consistency."""
    return datetime.now(timezone.utc)


def short_id(prefix: str = "") -> str:
    """A short, URL-safe id (first 12 hex of a uuid4)."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"
