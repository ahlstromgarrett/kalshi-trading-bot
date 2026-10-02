from __future__ import annotations

import logging
import uuid

from ..client import KalshiClient
from ..risk import AccountSnapshot
from ..strategy.base import TradeSignal

logger = logging.getLogger(__name__)


class LiveBroker:
    """Places real orders on Kalshi. Only instantiate this when you mean it."""

    def __init__(self, client: KalshiClient):
        self.client = client

    def open_positions_count(self) -> int:
        resp = self.client.get_positions(settlement_status="unsettled")
        positions = resp.get("market_positions", [])
        return sum(1 for p in positions if p.get("position_fp", "0") not in ("0", "0.00"))

    def total_exposure_dollars(self) -> float:
        resp = self.client.get_positions(settlement_status="unsettled")
        positions = resp.get("market_positions", [])
        return sum(abs(float(p.get("market_exposure_dollars", 0))) for p in positions)

    def get_account_snapshot(self) -> AccountSnapshot:
        # Deliberately not using the API's 'portfolio_value' field here -- its
        # docs don't clearly say whether it includes cash or not, and a real
        # test call returned 0 with zero open positions while cash was $47,
        # which only makes sense if it's position-value-only. Computing
        # equity as cash + our own exposure total sidesteps that ambiguity
        # entirely and matches how PaperBroker computes it.
        bal = self.client.get_balance()
        cash_dollars = bal.get("balance", 0) / 100.0
        equity_dollars = cash_dollars + self.total_exposure_dollars()
        return AccountSnapshot(cash_dollars=cash_dollars, equity_dollars=equity_dollars)

    def execute(self, signal: TradeSignal) -> dict:
        logger.info(
            "LIVE ORDER %s %s %.2f @ %.3f (reason: %s)",
            signal.ticker, signal.side, signal.count, signal.limit_price, signal.reason,
        )
        result = self.client.create_order(
            ticker=signal.ticker,
            side=signal.side,
            count=f"{signal.count:.2f}",
            price=f"{signal.limit_price:.4f}",
            time_in_force="immediate_or_cancel",
            client_order_id=str(uuid.uuid4()),
        )
        logger.info("LIVE ORDER RESULT: %s", result)
        return result
