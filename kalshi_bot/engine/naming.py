from __future__ import annotations

import logging

from ..client import KalshiClient

logger = logging.getLogger(__name__)

_event_title_cache: dict[str, str] = {}


def resolve_display_title(client: KalshiClient, event_ticker: str, fallback_title: str) -> str:
    """A short, human-readable label for a trade, e.g. "Oil Price (WTI) on Oct 1, 2026?"
    instead of the raw ticker. Only called for trades actually taken (not every
    scanned candidate), and cached per event_ticker since one event covers many
    strikes/markets that all share the same title.
    """
    if event_ticker in _event_title_cache:
        return _event_title_cache[event_ticker]

    title = fallback_title
    try:
        event = client.get_event(event_ticker).get("event", {})
        title = event.get("title") or fallback_title
    except Exception:
        logger.warning("Could not fetch event title for %s, falling back to market title", event_ticker)

    _event_title_cache[event_ticker] = title
    return title
