from __future__ import annotations

import logging

from ..client import KalshiClient
from ..ledger import Ledger

logger = logging.getLogger(__name__)

CHUNK_SIZE = 100


def check_settlements(client: KalshiClient, ledger: Ledger, mode: str) -> None:
    """Looks up each open ledger trade's real market outcome and, once the
    market has settled, records Won/Lost + payout. Runs for paper trades too
    -- paper mode watches real market data, it just never placed a real order.
    """
    open_trades = ledger.get_open_trades(mode=mode)
    if not open_trades:
        return

    tickers = list({t["ticker"] for t in open_trades})
    status_by_ticker: dict[str, dict] = {}
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i:i + CHUNK_SIZE]
        try:
            resp = client.get_markets(tickers=",".join(chunk))
        except Exception:
            logger.exception("Failed to fetch market status for settlement check")
            continue
        for m in resp.get("markets", []):
            status_by_ticker[m["ticker"]] = m

    for trade in open_trades:
        market = status_by_ticker.get(trade["ticker"])
        if market is None:
            continue

        # Checking for a populated result (not a specific status string) is the
        # robust signal here -- a real market returned status='finalized' for a
        # resolved market, not 'settled' as the docs' status-filter enum implied.
        result = market.get("result")  # 'yes' or 'no' once resolved, '' until then
        if not result:
            continue
        won = (trade["side"] == "bid" and result == "yes") or (trade["side"] == "ask" and result == "no")
        payout = trade["count"] * 1.0 if won else 0.0
        status = "Won" if won else "Lost"

        ledger.record_settlement(trade["id"], status, payout)
        logger.info(
            "SETTLED %s trade #%d %s: result=%s -> %s, payout=$%.2f, pnl=$%.2f",
            mode, trade["id"], trade["ticker"], result, status, payout, payout - trade["cost"],
        )
