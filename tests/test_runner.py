import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_bot.config import RiskLimits
from kalshi_bot.engine.runner import Runner
from kalshi_bot.ledger import Ledger
from kalshi_bot.risk import AccountSnapshot, RiskManager
from kalshi_bot.strategy.base import TradeSignal


class FakeBroker:
    def __init__(self, equity=1000.0):
        self.equity = equity
        self.executed = []

    def open_positions_count(self):
        return len(self.executed)

    def total_exposure_dollars(self):
        return sum(s.count * s.true_price for s in self.executed)

    def get_account_snapshot(self):
        return AccountSnapshot(cash_dollars=self.equity, equity_dollars=self.equity)

    def execute(self, signal):
        self.executed.append(signal)


class FakeStrategy:
    def __init__(self, signals):
        self.signals = signals

    def generate_signals(self, snapshots):
        return self.signals


def make_runner(tmp_path, signals, mode="paper"):
    ledger = Ledger(db_path=tmp_path / "test_ledger.db")
    risk = RiskManager(RiskLimits())
    broker = FakeBroker()
    strategy = FakeStrategy(signals)
    runner = Runner(client=None, strategy=strategy, risk=risk, broker=broker,
                     max_hours_to_close=24, ledger=ledger, mode=mode)
    return runner, broker, ledger


def patch_no_ops(monkeypatch):
    import kalshi_bot.engine.runner as runner_module
    monkeypatch.setattr(runner_module, "check_settlements", lambda *a, **k: None)
    monkeypatch.setattr(runner_module, "scan_open_markets", lambda *a, **k: [])
    monkeypatch.setattr(runner_module, "resolve_display_title", lambda client, event_ticker, fallback: fallback)


def test_only_one_trade_taken_per_event_in_a_single_pass(tmp_path, monkeypatch):
    patch_no_ops(monkeypatch)
    signals = [
        TradeSignal(ticker="WTI-95", title="WTI?", event_ticker="WTI-EVENT", side="bid",
                    limit_price=0.95, true_price=0.95, reason="r"),
        TradeSignal(ticker="WTI-96", title="WTI?", event_ticker="WTI-EVENT", side="bid",
                    limit_price=0.96, true_price=0.96, reason="r"),
        TradeSignal(ticker="GOLD-99", title="Gold?", event_ticker="GOLD-EVENT", side="bid",
                    limit_price=0.92, true_price=0.92, reason="r"),
    ]
    runner, broker, ledger = make_runner(tmp_path, signals)
    runner.run_once()

    assert len(broker.executed) == 2
    executed_events = {s.event_ticker for s in broker.executed}
    assert executed_events == {"WTI-EVENT", "GOLD-EVENT"}


def test_event_already_open_from_a_prior_pass_is_skipped(tmp_path, monkeypatch):
    patch_no_ops(monkeypatch)
    ledger = Ledger(db_path=tmp_path / "test_ledger.db")
    ledger.record_trade_open(mode="paper", ticker="WTI-95", event_ticker="WTI-EVENT",
                              side="bid", price=0.95, count=10, reason="earlier pass")

    risk = RiskManager(RiskLimits())
    broker = FakeBroker()
    signals = [
        TradeSignal(ticker="WTI-96", title="WTI?", event_ticker="WTI-EVENT", side="bid",
                    limit_price=0.96, true_price=0.96, reason="r"),
    ]
    runner = Runner(client=None, strategy=FakeStrategy(signals), risk=risk, broker=broker,
                     max_hours_to_close=24, ledger=ledger, mode="paper")
    runner.run_once()

    assert len(broker.executed) == 0
