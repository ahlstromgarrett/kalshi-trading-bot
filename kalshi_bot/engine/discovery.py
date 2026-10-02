from __future__ import annotations

import logging
import time
from typing import List

from ..client import KalshiClient
from ..strategy.base import MarketSnapshot

logger = logging.getLogger(__name__)


def scan_open_markets(client: KalshiClient, max_hours_to_close: float,
                       max_pages: int = 20, page_size: int = 1000) -> List[MarketSnapshot]:
    """Pulls every open market closing within the window, across all categories.

    We trade "anything that meets the base requirements," so unlike a fixed
    ticker list this has to page through the whole open-markets list each
    pass. Filters server-side by close time where the API supports it
    (max_close_ts); binary-vs-scalar filtering happens client-side since the
    endpoint doesn't expose that as a query param.
    """
    horizon_ts = int(time.time() + max_hours_to_close * 3600)
    snapshots: List[MarketSnapshot] = []
    cursor = None

    for _ in range(max_pages):
        params = {"status": "open", "limit": page_size, "max_close_ts": horizon_ts}
        if cursor:
            params["cursor"] = cursor

        try:
            resp = client.get_markets(**params)
        except Exception:
            logger.exception("Failed to fetch markets page, stopping scan for this pass")
            break

        markets = resp.get("markets", [])
        for m in markets:
            if m.get("market_type") != "binary":
                continue
            snapshots.append(MarketSnapshot(
                ticker=m["ticker"],
                title=m.get("title", ""),
                event_ticker=m.get("event_ticker", ""),
                market_type=m.get("market_type", ""),
                yes_bid=float(m.get("yes_bid_dollars") or 0),
                yes_ask=float(m.get("yes_ask_dollars") or 0),
                no_bid=float(m.get("no_bid_dollars") or 0),
                no_ask=float(m.get("no_ask_dollars") or 0),
                close_time=m.get("close_time", ""),
                volume=float(m.get("volume_fp") or 0),
            ))

        cursor = resp.get("cursor")
        if not cursor or not markets:
            break

    logger.debug("Scanned %d open binary markets closing within %.0fh", len(snapshots), max_hours_to_close)
    return snapshots
