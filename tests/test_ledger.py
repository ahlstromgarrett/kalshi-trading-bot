import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_bot.ledger import Ledger


def make_ledger(tmp_path) -> Ledger:
    return Ledger(db_path=tmp_path / "test_ledger.db")


def test_record_and_settle_a_winning_trade(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_deposit(amount=40, source="Personal", mode="paper")

    trade_id = ledger.record_trade_open(
        mode="paper", ticker="TEST-MKT", side="bid", price=0.95, count=10, reason="test",
    )
    ledger.record_settlement(trade_id, "Won", payout=10.0)

    trades = ledger.get_trade_log(mode="paper")
    assert len(trades) == 1
    assert trades[0]["status"] == "Won"
    assert trades[0]["cost"] == 9.5
    assert trades[0]["pnl"] == 0.5

    stats = ledger.get_dashboard_stats(mode="paper")
    assert stats["total_deposited"] == 40
    assert stats["total_trading_profit"] == 0.5
    assert stats["current_balance"] == 40.5
    assert stats["won"] == 1
    assert stats["overall_win_rate"] == 1.0


def test_open_trade_does_not_count_toward_profit(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_deposit(amount=100, mode="paper")
    ledger.record_trade_open(mode="paper", ticker="X", side="bid", price=0.9, count=5, reason="r")

    stats = ledger.get_dashboard_stats(mode="paper")
    assert stats["open"] == 1
    assert stats["total_trading_profit"] == 0.0
    assert stats["current_balance"] == 100.0


def test_mode_filters_are_isolated(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_trade_open(mode="paper", ticker="X", side="bid", price=0.9, count=5, reason="r")
    ledger.record_trade_open(mode="live", ticker="Y", side="bid", price=0.9, count=5, reason="r")

    assert len(ledger.get_trade_log(mode="paper")) == 1
    assert len(ledger.get_trade_log(mode="live")) == 1
    assert len(ledger.get_trade_log()) == 2


def test_deposits_are_mode_isolated_too(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_deposit(amount=1000, mode="paper", source="Paper seed")
    ledger.record_deposit(amount=25, mode="live", source="Personal")

    assert len(ledger.get_deposits(mode="paper")) == 1
    assert len(ledger.get_deposits(mode="live")) == 1
    assert ledger.get_dashboard_stats(mode="live")["total_deposited"] == 25
    assert ledger.get_dashboard_stats(mode="paper")["total_deposited"] == 1000


def test_daily_summary_tracks_running_balance(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_deposit(amount=40, mode="paper")  # defaults to today, same day as the trade below

    t1 = ledger.record_trade_open(mode="paper", ticker="A", side="bid", price=0.9, count=10, reason="r")
    ledger.record_settlement(t1, "Won", payout=10.0)  # +1.0 pnl

    daily = ledger.get_daily_summary(mode="paper")
    assert len(daily) == 1
    assert daily[0]["deposits_added"] == 40
    # Starting balance includes the same-day deposit (matches the user's
    # spreadsheet: a deposit on day 1 makes day 1's starting balance the
    # deposit amount, not $0 before it landed).
    assert daily[0]["starting_balance"] == 40.0
    assert daily[0]["daily_pnl"] == 1.0
    assert daily[0]["ending_balance"] == 41.0


def test_second_day_starts_from_first_days_ending_balance(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.record_deposit(amount=40, mode="paper", date="2026-09-30T12:00:00+00:00")
    t1 = ledger.record_trade_open(mode="paper", ticker="A", side="bid", price=0.9, count=10, reason="r")
    with ledger._connect() as conn:
        conn.execute("UPDATE trades SET opened_at = ? WHERE id = ?", ("2026-09-30T12:00:00+00:00", t1))
    ledger.record_settlement(t1, "Won", payout=10.0)
    with ledger._connect() as conn:
        conn.execute("UPDATE trades SET settled_at = ? WHERE id = ?", ("2026-09-30T13:00:00+00:00", t1))

    t2 = ledger.record_trade_open(mode="paper", ticker="B", side="bid", price=0.9, count=5, reason="r")
    with ledger._connect() as conn:
        conn.execute("UPDATE trades SET opened_at = ? WHERE id = ?", ("2026-10-01T12:00:00+00:00", t2))

    daily = ledger.get_daily_summary(mode="paper")
    assert len(daily) == 2
    assert daily[0]["date"] == "2026-09-30"
    assert daily[0]["starting_balance"] == 40.0
    assert daily[0]["ending_balance"] == 41.0
    assert daily[1]["date"] == "2026-10-01"
    assert daily[1]["starting_balance"] == 41.0  # carries over, not reset to 0
