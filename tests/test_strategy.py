import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_bot.config import StrategyConfig
from kalshi_bot.strategy.base import MarketSnapshot
from kalshi_bot.strategy.manual_replica import ManualReplicaStrategy


def snapshot(**overrides) -> MarketSnapshot:
    defaults = dict(
        ticker="TEST-MKT",
        title="Test Market?",
        event_ticker="TEST-EVENT",
        market_type="binary",
        yes_bid=0.10,
        yes_ask=0.12,
        no_bid=0.88,
        no_ask=0.90,
        close_time=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        volume=100,
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def make_strategy(**overrides) -> ManualReplicaStrategy:
    config = StrategyConfig(min_probability=0.90, max_probability=0.99,
                             max_hours_to_close=24, min_minutes_to_close=5)
    for k, v in overrides.items():
        setattr(config, k, v)
    return ManualReplicaStrategy(config)


def test_buys_yes_when_yes_ask_above_threshold():
    strat = make_strategy()
    snap = snapshot(yes_ask=0.95, no_ask=0.10)
    signals = strat.generate_signals([snap])
    assert len(signals) == 1
    assert signals[0].side == "bid"
    assert signals[0].limit_price == 0.95


def test_buys_no_when_no_ask_above_threshold():
    strat = make_strategy()
    snap = snapshot(yes_bid=0.05, yes_ask=0.08, no_ask=0.95)
    signals = strat.generate_signals([snap])
    assert len(signals) == 1
    assert signals[0].side == "ask"
    assert signals[0].limit_price == 0.05  # sells yes at yes_bid == buys no at no_ask


def test_skips_when_neither_side_meets_threshold():
    strat = make_strategy()
    snap = snapshot(yes_ask=0.60, no_ask=0.45)
    assert strat.generate_signals([snap]) == []


def test_skips_when_price_is_at_the_ceiling_with_no_margin_left():
    strat = make_strategy()
    snap = snapshot(yes_ask=1.00, no_ask=0.0)
    assert strat.generate_signals([snap]) == []


def test_signal_carries_event_ticker_for_correlation_dedup():
    strat = make_strategy()
    snap = snapshot(yes_ask=0.95, no_ask=0.10, event_ticker="WTI-EVENT")
    signals = strat.generate_signals([snap])
    assert signals[0].event_ticker == "WTI-EVENT"


def test_skips_scalar_markets():
    strat = make_strategy()
    snap = snapshot(market_type="scalar", yes_ask=0.99)
    assert strat.generate_signals([snap]) == []


def test_skips_markets_closing_too_soon():
    strat = make_strategy(min_minutes_to_close=10)
    snap = snapshot(yes_ask=0.99, close_time=(datetime.now(timezone.utc) + timedelta(minutes=2))
                     .isoformat().replace("+00:00", "Z"))
    assert strat.generate_signals([snap]) == []


def test_skips_markets_closing_too_far_out():
    strat = make_strategy(max_hours_to_close=24)
    snap = snapshot(yes_ask=0.99, close_time=(datetime.now(timezone.utc) + timedelta(hours=48))
                     .isoformat().replace("+00:00", "Z"))
    assert strat.generate_signals([snap]) == []
