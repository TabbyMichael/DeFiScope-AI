"""Curated reference data loaded from ``services/api/data/*.json``.

Kept separate from the analysis logic so the mappings (which protocol mints
which stablecoin) are a *data* concern: adding or correcting an entry is a
JSON edit, not a code change. Loaders are cached at process level since the
files are static at runtime.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def load_stablecoin_mapping() -> dict[str, dict[str, str]]:
    """Return ``{protocol_slug: {symbol: coins.llama.fi coin-id}}``.

    A missing or malformed file degrades to an empty map, so the depeg watch
    simply reports 'no tracked stablecoin' for every protocol rather than
    crashing the crawl. Non-dict entries (e.g. the ``_comment`` key) are
    ignored."""
    path = _DATA_DIR / "protocol_stablecoins.json"
    if not path.exists():
        logger.warning("Stablecoin mapping file missing at %s", path)
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read stablecoin mapping: %s", exc)
        return {}
    return {slug: coins for slug, coins in raw.items() if isinstance(coins, dict)}
