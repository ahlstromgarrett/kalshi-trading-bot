from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from .config import RiskLimits

logger = logging.getLogger(__name__)

KILL_SWITCH_FILE = Path(__file__).resolve().parent.parent / "STOP"


@dataclass
class TradeIntent:
    ticker: str
    side: str  # 'bid' or 'ask'
    count: float
    price: float  # dollars per contract, 0-1

    @property
    def notional_dollars(self) -> float:
        return self.count * self.price


@dataclass
class AccountSnapshot:
    cash_dollars: float    # spendable cash right now
    equity_dollars: float  # cash + value of open positions -- used for fraction-based limits


class RiskViolation(Exception):
    pass


class RiskManager:
    """Hard limits enforced on every trade intent regardless of what the strategy wants.

    These are a backstop, not the strategy's own logic. A strategy bug or bad
    signal should never be able to blow past these numbers. Daily loss is
    measured against equity (not a tracked pnl total) so it reflects real
    account drawdown, including open positions, from whichever broker is used.
    """

    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self._day: Optional[date] = None
        self._day_start_equity: Optional[float] = None

    def note_equity(self, equity_dollars: float) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._day_start_equity = equity_dollars

    def check_kill_switch(self) -> None:
        if KILL_SWITCH_FILE.exists():
            raise RiskViolation(
                f"Kill switch active: {KILL_SWITCH_FILE} exists. Delete it to resume trading."
            )

    def check_intent(self, intent: TradeIntent, account: AccountSnapshot,
                      current_open_positions: int, current_total_exposure_dollars: float) -> None:
        self.check_kill_switch()

        max_position_dollars = account.equity_dollars * self.limits.max_position_fraction
        if intent.notional_dollars > max_position_dollars:
            raise RiskViolation(
                f"{intent.ticker}: order notional ${intent.notional_dollars:.2f} exceeds "
                f"max_position_fraction ({self.limits.max_position_fraction:.0%} of equity "
                f"= ${max_position_dollars:.2f})"
            )

        max_total_exposure_dollars = account.equity_dollars * self.limits.max_total_exposure_fraction
        projected_exposure = current_total_exposure_dollars + intent.notional_dollars
        if projected_exposure > max_total_exposure_dollars:
            raise RiskViolation(
                f"Projected total exposure ${projected_exposure:.2f} exceeds "
                f"max_total_exposure_fraction ({self.limits.max_total_exposure_fraction:.0%} of equity "
                f"= ${max_total_exposure_dollars:.2f})"
            )

        if current_open_positions >= self.limits.max_open_positions:
            raise RiskViolation(
                f"Already at max_open_positions ({self.limits.max_open_positions})"
            )

        if intent.notional_dollars > account.cash_dollars:
            raise RiskViolation(
                f"{intent.ticker}: order notional ${intent.notional_dollars:.2f} exceeds "
                f"available cash ${account.cash_dollars:.2f}"
            )

        if self._day_start_equity is not None:
            loss_today = self._day_start_equity - account.equity_dollars
            max_daily_loss_dollars = self._day_start_equity * self.limits.max_daily_loss_fraction
            if loss_today >= max_daily_loss_dollars:
                raise RiskViolation(
                    f"Drawdown today ${loss_today:.2f} has hit max_daily_loss_fraction "
                    f"({self.limits.max_daily_loss_fraction:.0%} of day-start equity "
                    f"= ${max_daily_loss_dollars:.2f})"
                )
