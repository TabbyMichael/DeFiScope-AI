"""Curated reference data loaded from ``services/api/data/*.json``.

Kept separate from the analysis logic so the mappings (which protocol mints
which stablecoin, which contracts a protocol is measured on) are a *data*
concern: adding or correcting an entry is a JSON edit, not a code change.
Loaders are cached at process level since the files are static at runtime.
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


@lru_cache(maxsize=1)
def load_dune_mapping() -> dict[str, dict[str, list[str]]]:
    """Return ``{protocol_slug: {chain: [contract address, ...]}}``.

    The chain key is the *query* chain - the Dune table namespace the saved
    query reads (``ethereum.transactions``) - not DefiLlama's TVL attribution:
    a protocol can hold TVL on ten chains while its contracts are only
    deployed on two.

    A missing entry means "not measured on-chain yet", and the caller must
    report that as a data gap. Wrong addresses would produce clean-looking,
    wrong numbers, so the file is curated conservatively (see its ``_comment``)
    and keys beginning with ``_`` are documentation, skipped on load."""
    path = _DATA_DIR / "protocol_dune.json"
    if not path.exists():
        logger.warning("Dune contract mapping file missing at %s", path)
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read Dune contract mapping: %s", exc)
        return {}

    mapping: dict[str, dict[str, list[str]]] = {}
    for slug, chains in raw.items():
        if slug.startswith("_") or not isinstance(chains, dict):
            continue
        per_chain = {
            chain: [addr for addr in addresses if isinstance(addr, str)]
            for chain, addresses in chains.items()
            if isinstance(addresses, list)
        }
        per_chain = {chain: addrs for chain, addrs in per_chain.items() if addrs}
        if per_chain:
            mapping[slug] = per_chain
    return mapping
