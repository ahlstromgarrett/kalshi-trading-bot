from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class MarketSnapshot:
    ticker: str
    title: str  # human-readable question, e.g. "Will WTI crude be above $95.99 on Oct 1, 2026?"
    event_ticker: str  # groups related strikes/contracts on the same underlying event
    market_type: str  # 'binary' or 'scalar'
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    close_time: str  # ISO 8601, e.g. "2026-09-30T18:00:00Z"
    volume: float

    @property
    def close_datetime(self) -> Optional[datetime]:
        if not self.close_time:
            return None
        try:
            return datetime.fromisoformat(self.close_time.replace("Z", "+00:00"))
        except ValueError:
            return None

    def minutes_to_close(self, now: Optional[datetime] = None) -> Optional[float]:
        close_dt = self.close_datetime
        if close_dt is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (close_dt - now).total_seconds() / 60.0


@dataclass
class TradeSignal:
    ticker: str
    title: str
    event_ticker: str
    side: str  # 'bid' (buy yes) or 'ask' (sell yes == buy no)
    limit_price: float  # the price sent to Kalshi's order API, 0-1 -- see true_price below
    true_price: float  # the REAL cost/probability of the side actually being bought, 0-1
    reason: str  # human-readable justification, logged for every trade
    count: Optional[float] = None  # filled in by the runner based on account size

    # For a 'bid' order (buying yes), limit_price == true_price == yes_ask: you pay
    # yes_ask per contract and that's also the market's implied probability of yes.
    #
    # For an 'ask' order (buying no by selling yes), Kalshi's API only ever quotes
    # in yes-terms, so limit_price must be yes_bid (the real order sent, to cross
    # and fill against the resting yes bid). But the actual dollar cost of that
    # trade is no_ask = 1 - yes_bid per contract, not yes_bid. true_price carries
    # that real number. Sizing, risk, and ledger cost MUST use true_price, never
    # limit_price, or a 'buy no' trade near $0.99 confidence looks ~100x cheaper
    # than it really is and gets wildly oversized.


class Strategy(ABC):
    """Implement this once we've formalized your manual trading rules."""

    @abstractmethod
    def generate_signals(self, snapshots: List[MarketSnapshot]) -> List[TradeSignal]:
        ...
