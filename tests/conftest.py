"""Shared test setup: make server/ and analyzer/ importable, and point the app at SQLite.

Must run before any `app.*` import so the engine picks up the SQLite URL. pytest imports
conftest.py first, so setting the env here is sufficient.
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(_ROOT, "server"))
sys.path.insert(0, os.path.join(_ROOT, "analyzer"))

# A file-based SQLite db (shared across the threadpool connections) for unit tests.
_DB_PATH = os.path.join(tempfile.gettempdir(), "minidrop_test.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ.setdefault("MINIDROP_DATABASE_URL", f"sqlite+pysqlite:///{_DB_PATH}")
os.environ.setdefault("MINIDROP_ARTIFACTS_DIR", os.path.join(tempfile.gettempdir(), "minidrop_artifacts"))
# Speed up the offline monitor a touch in tests.
os.environ.setdefault("MINIDROP_MONITOR_INTERVAL", "1")
