"""Make the backend importable when a fuzzer runs, without touching real data."""

import os
import sys
import tempfile

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if os.path.isdir(_BACKEND) and _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# database.py opens DATABASE_PATH at import time; keep it in a throwaway dir.
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.mkdtemp(prefix="kiosk-fuzz-"), "kiosk.db"))
os.environ.setdefault("SECRET_KEY", "fuzzing-only-secret-key-0123456789abcdef")
