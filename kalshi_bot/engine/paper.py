from __future__ import annotations

import logging

from ..ledger import Ledger
from ..risk import AccountSnapshot
from ..strategy.base import TradeSignal

logger = logging.getLogger(__name__)


class PaperBroker:
    """Simulates fills without touching the real Kalshi account.

    Every trade this strategy takes is held to settlement (no early exits in
    the historical data this was built from), so "closing a position" here
    means the ledger's settlement check marking it Won/Lost -- not an
    opposite trade netting it out. Cash and exposure are therefore derived
    directly from the ledger (the single source of truth also used by the
    dashboard) rather than tracked separately here, so paper mode can never
    drift out of sync with what the ledger reports: cash only ever reflects
    seed cash minus money spent on trades ever opened, plus payouts actually
    received back on settlement.

    The seed cash is recorded once as a mode='paper' ledger deposit (mirroring
    how the dashboard already computes balance as deposits + trading profit),
    not re-read from the live account on every restart -- otherwise the
    simulation's anchor would silently shift each time the bot restarts if
    the real account's balance had moved in the meantime.
    """

    def __init__(self, ledger: Ledger, default_seed_cash: float = 1000.0):
        self.ledger = ledger
        if not ledger.get_deposits(mode="paper"):
            ledger.record_deposit(
                amount=default_seed_cash,
                source="Paper seed (mirrored live balance at first run)",
                mode="paper",
            )

    def _cash_dollars(self) -> float:
        seeded = sum(d["amount"] for d in self.ledger.get_deposits(mode="paper"))
        trades = self.ledger.get_trade_log(mode="paper", limit=1_000_000)
        spent = sum(t["cost"] for t in trades)
        returned = sum(
            t["payout"] or 0.0 for t in trades if t["status"] in ("Won", "Lost", "Cashed Out")
        )
        return seeded - spent + returned

    def _open_cost_dollars(self) -> float:
        return sum(t["cost"] for t in self.ledger.get_open_trades(mode="paper"))

    def open_positions_count(self) -> int:
        return len(self.ledger.get_open_trades(mode="paper"))

    def total_exposure_dollars(self) -> float:
        return self._open_cost_dollars()

    def get_account_snapshot(self) -> AccountSnapshot:
        cash = self._cash_dollars()
        return AccountSnapshot(cash_dollars=cash, equity_dollars=cash + self._open_cost_dollars())

    def execute(self, signal: TradeSignal) -> None:
        # No state to mutate here -- Runner calls ledger.record_trade_open right
        # after this, and every balance figure above is derived live from the
        # ledger, so that single write is enough to keep everything consistent.
        logger.info(
            "PAPER FILL %s %s %.2f @ true_price %.3f (order price %.3f, reason: %s)",
            signal.ticker, signal.side, signal.count, signal.true_price,
            signal.limit_price, signal.reason,
        )
