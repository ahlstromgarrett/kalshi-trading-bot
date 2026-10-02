from __future__ import annotations

import logging
import sys
import time
from typing import Protocol

from ..client import KalshiClient
from ..ledger import Ledger
from ..risk import AccountSnapshot, RiskManager, RiskViolation, TradeIntent
from ..sizing import size_contracts
from ..strategy.base import Strategy, TradeSignal
from .discovery import scan_open_markets
from .naming import resolve_display_title
from .settlement import check_settlements

logger = logging.getLogger(__name__)


class Broker(Protocol):
    def open_positions_count(self) -> int: ...
    def total_exposure_dollars(self) -> float: ...
    def get_account_snapshot(self) -> AccountSnapshot: ...
    def execute(self, signal: TradeSignal) -> object: ...


class Runner:
    def __init__(self, client: KalshiClient, strategy: Strategy, risk: RiskManager,
                 broker: Broker, max_hours_to_close: float, ledger: Ledger, mode: str):
        self.client = client
        self.strategy = strategy
        self.risk = risk
        self.broker = broker
        self.max_hours_to_close = max_hours_to_close
        self.ledger = ledger
        self.mode = mode

    def run_once(self) -> None:
        self.risk.check_kill_switch()

        check_settlements(self.client, self.ledger, self.mode)

        account = self.broker.get_account_snapshot()
        self.risk.note_equity(account.equity_dollars)

        snapshots = scan_open_markets(self.client, self.max_hours_to_close)
        signals = self.strategy.generate_signals(snapshots)
        # INFO (not debug) so this line always lands in logs/bot.log -- a watchdog
        # process can check its timestamp to tell "quiet, no qualifying markets
        # right now" apart from "the process is actually dead."
        logger.info(
            "Heartbeat: scanned %d markets, %d signals, equity=$%.2f",
            len(snapshots), len(signals), account.equity_dollars,
        )
        if not signals:
            return

        open_positions = self.broker.open_positions_count()
        total_exposure = self.broker.total_exposure_dollars()
        cash = account.cash_dollars

        # One open position per event at a time -- multiple strikes on the same
        # underlying event are correlated bets, not independent diversification,
        # even though they show up as separate markets/tickers.
        open_events = {t["event_ticker"] for t in self.ledger.get_open_trades(mode=self.mode)}

        for signal in signals:
            if signal.event_ticker and signal.event_ticker in open_events:
                logger.debug(
                    "Skipping %s: already have an open position in event %s",
                    signal.ticker, signal.event_ticker,
                )
                continue

            count = size_contracts(
                equity_dollars=account.equity_dollars,
                cash_dollars=cash,
                position_fraction=self.risk.limits.position_fraction,
                max_position_fraction=self.risk.limits.max_position_fraction,
                price=signal.true_price,
            )
            if count < 1:
                logger.debug("Skipping %s: sizing rounds to 0 contracts", signal.ticker)
                continue
            signal.count = count

            intent = TradeIntent(
                ticker=signal.ticker, side=signal.side,
                count=signal.count, price=signal.true_price,
            )
            try:
                self.risk.check_intent(
                    intent,
                    AccountSnapshot(cash_dollars=cash, equity_dollars=account.equity_dollars),
                    open_positions, total_exposure,
                )
            except RiskViolation as e:
                logger.warning("Signal blocked by risk manager: %s", e)
                continue

            self.broker.execute(signal)
            display_title = resolve_display_title(self.client, signal.event_ticker, signal.title)
            self.ledger.record_trade_open(
                mode=self.mode, ticker=signal.ticker, side=signal.side,
                price=signal.true_price, count=signal.count, reason=signal.reason,
                event_ticker=signal.event_ticker, market_title=display_title,
            )
            total_exposure += intent.notional_dollars
            cash -= intent.notional_dollars
            open_positions += 1
            if signal.event_ticker:
                open_events.add(signal.event_ticker)

    def run_forever(self, interval_seconds: float = 30.0) -> None:
        logger.info("Runner starting, polling every %.0fs. Ctrl+C to stop.", interval_seconds)
        while True:
            try:
                self.run_once()
            except RiskViolation as e:
                # Deliberate stop (kill switch, etc). Exit 0 so a launchd job
                # configured with KeepAlive->SuccessfulExit:false does NOT
                # resurrect it -- an intentional halt must stay halted until a
                # human removes the STOP file and restarts it themselves.
                logger.error("Halting: %s", e)
                sys.exit(0)
            except Exception:
                logger.exception("Unexpected error in run_once, continuing")
            time.sleep(interval_seconds)
