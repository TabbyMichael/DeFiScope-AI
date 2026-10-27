"""Isolate tests from the developer's local SQLite file."""

import os

os.environ.setdefault("DEFISCOPE_DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("DEFISCOPE_OPENAI_API_KEY", "")
os.environ.setdefault("DEFISCOPE_DEFAULT_PROTOCOLS", "test-protocol")
