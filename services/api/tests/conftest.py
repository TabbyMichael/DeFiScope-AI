"""Isolate tests from the developer's local SQLite file."""

import os

os.environ.setdefault("DEFISCOPE_DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("DEFISCOPE_OPENAI_API_KEY", "")
os.environ.setdefault("DEFISCOPE_DEFAULT_PROTOCOLS", "test-protocol")
# Keep integration tests on the curated list only; watchlist discovery is
# covered separately in test_watchlist.py.
os.environ.setdefault("DEFISCOPE_MARKET_TOP_N", "0")
