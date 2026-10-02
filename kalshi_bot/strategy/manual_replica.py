from __future__ import annotations

import logging
from typing import List

from ..config import StrategyConfig
from .base import MarketSnapshot, Strategy, TradeSignal

logger = logging.getLogger(__name__)


class ManualReplicaStrategy(Strategy):
    """Base rule learned from your manual trading: take the high-probability
    side of any binary market that settles soon, diversified across as many
    qualifying markets as show up per day.

    A market qualifies when:
      - it's binary (yes/no), not scalar
      - it closes within [min_minutes_to_close, max_hours_to_close] from now
      - one side (yes or no) is priced in [min_probability, max_probability] --
        the ceiling excludes prices with no real margin left (e.g. exactly
        $1.00, which nets $0 even on a win once fees are counted)

    This is the base rule from analyzing your trade history (154 winning
    trades buying 90-99c yes/no contracts on same-day settling markets).
    Position sizing and per-trade/day risk caps live in RiskManager, not
    here -- this only decides *what* to trade, not *how much*.
    """

    def __init__(self, config: StrategyConfig):
        self.config = config

    def generate_signals(self, snapshots: List[MarketSnapshot]) -> List[TradeSignal]:
        signals = []
        for snap in snapshots:
            if snap.market_type != "binary":
                continue

            minutes_left = snap.minutes_to_close()
            if minutes_left is None:
                continue
            if minutes_left < self.config.min_minutes_to_close:
                continue
            if minutes_left > self.config.max_hours_to_close * 60:
                continue

            if self.config.min_probability <= snap.yes_ask <= self.config.max_probability:
                signals.append(TradeSignal(
                    ticker=snap.ticker,
                    title=snap.title,
                    event_ticker=snap.event_ticker,
                    side="bid",
                    limit_price=snap.yes_ask,
                    true_price=snap.yes_ask,
                    reason=(
                        f"yes_ask {snap.yes_ask:.2f} in [{self.config.min_probability:.2f}, "
                        f"{self.config.max_probability:.2f}], {minutes_left:.0f}min to close"
                    ),
                ))
            elif self.config.min_probability <= snap.no_ask <= self.config.max_probability:
                # Buying NO at no_ask means placing an order to sell YES at yes_bid
                # (that's the only way Kalshi's order API expresses it), but the real
                # dollar cost per contract is no_ask, not yes_bid -- see TradeSignal.
                signals.append(TradeSignal(
                    ticker=snap.ticker,
                    title=snap.title,
                    event_ticker=snap.event_ticker,
                    side="ask",
                    limit_price=snap.yes_bid,
                    true_price=snap.no_ask,
                    reason=(
                        f"no_ask {snap.no_ask:.2f} in [{self.config.min_probability:.2f}, "
                        f"{self.config.max_probability:.2f}], {minutes_left:.0f}min to close"
                    ),
                ))
        return signals
