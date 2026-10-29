#!/usr/bin/env python
"""Dump the FastAPI OpenAPI schema to ``services/api/openapi.json``.

The frontend's ``lib/api-types.ts`` is generated from this artifact, so the API
contract is the single source of truth for TypeScript types (no hand-mirroring).

Run from anywhere:  ``uv run python scripts/export_openapi.py``
CI / drift check:  regenerate and ``git diff --exit-code openapi.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the package root (services/api) is importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def main() -> None:
    schema = app.openapi()
    out = ROOT / "openapi.json"
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI schema ({schema['info']['title']} v{schema['info']['version']}) -> {out}")


if __name__ == "__main__":
    main()
