import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from kalshi_bot.config import RiskLimits
from kalshi_bot.risk import AccountSnapshot, RiskManager, RiskViolation, TradeIntent


def make_manager(**overrides) -> RiskManager:
    limits = RiskLimits(
        position_fraction=0.03,
        max_position_fraction=0.08,
        max_total_exposure_fraction=0.60,
        max_daily_loss_fraction=0.15,
        max_open_positions=25,
    )
    for k, v in overrides.items():
        setattr(limits, k, v)
    return RiskManager(limits)


def account(cash=1000.0, equity=1000.0) -> AccountSnapshot:
    return AccountSnapshot(cash_dollars=cash, equity_dollars=equity)


def test_blocks_oversized_position():
    rm = make_manager(max_position_fraction=0.01)  # 1% of $1000 = $10
    intent = TradeIntent(ticker="X", side="bid", count=100, price=0.5)  # $50 notional
    with pytest.raises(RiskViolation):
        rm.check_intent(intent, account(), current_open_positions=0, current_total_exposure_dollars=0)


def test_blocks_exposure_over_cap():
    rm = make_manager(max_total_exposure_fraction=0.10)  # 10% of $1000 = $100
    intent = TradeIntent(ticker="X", side="bid", count=10, price=0.5)  # $5 notional
    with pytest.raises(RiskViolation):
        rm.check_intent(intent, account(), current_open_positions=0, current_total_exposure_dollars=96)


def test_blocks_at_max_open_positions():
    rm = make_manager(max_open_positions=2)
    intent = TradeIntent(ticker="X", side="bid", count=1, price=0.1)
    with pytest.raises(RiskViolation):
        rm.check_intent(intent, account(), current_open_positions=2, current_total_exposure_dollars=0)


def test_blocks_when_exceeds_available_cash():
    rm = make_manager()
    intent = TradeIntent(ticker="X", side="bid", count=100, price=0.5)  # $50 notional
    with pytest.raises(RiskViolation):
        rm.check_intent(intent, account(cash=10, equity=1000), current_open_positions=0,
                         current_total_exposure_dollars=0)


def test_blocks_after_daily_loss_limit_hit():
    rm = make_manager(max_daily_loss_fraction=0.10)
    rm.note_equity(1000.0)  # day-start equity
    intent = TradeIntent(ticker="X", side="bid", count=1, price=0.1)
    # Equity has dropped from $1000 to $880 -- a $120 drawdown, over the $100 (10%) limit.
    with pytest.raises(RiskViolation):
        rm.check_intent(intent, account(cash=880, equity=880), current_open_positions=0,
                         current_total_exposure_dollars=0)


def test_allows_reasonable_trade():
    rm = make_manager()
    intent = TradeIntent(ticker="X", side="bid", count=10, price=0.5)  # $5 notional
    rm.check_intent(intent, account(), current_open_positions=0, current_total_exposure_dollars=0)


def test_kill_switch_blocks_everything(tmp_path, monkeypatch):
    import kalshi_bot.risk as risk_module
    fake_stop = tmp_path / "STOP"
    fake_stop.write_text("halt")
    monkeypatch.setattr(risk_module, "KILL_SWITCH_FILE", fake_stop)

    rm = make_manager()
    intent = TradeIntent(ticker="X", side="bid", count=1, price=0.1)
    with pytest.raises(RiskViolation):
        rm.check_intent(intent, account(), current_open_positions=0, current_total_exposure_dollars=0)
