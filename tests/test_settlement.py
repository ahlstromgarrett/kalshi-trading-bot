import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_bot.engine.settlement import check_settlements
from kalshi_bot.ledger import Ledger


class FakeClient:
    def __init__(self, markets):
        self.markets = markets  # ticker -> market dict

    def get_markets(self, tickers, **kwargs):
        wanted = tickers.split(",")
        return {"markets": [m for t, m in self.markets.items() if t in wanted]}


def test_finalized_status_is_recognized_not_just_settled(tmp_path):
    # Regression test: a real Kalshi market returns status='finalized' with a
    # populated result for a resolved market, not 'settled' as the API's
    # status-filter enum names implied. This bug left 23 real resolved trades
    # stuck as 'Open' in the ledger until fixed.
    ledger = Ledger(db_path=tmp_path / "test_ledger.db")
    trade_id = ledger.record_trade_open(mode="paper", ticker="X", event_ticker="X-EVENT",
                                         side="bid", price=0.95, count=10, reason="test")
    client = FakeClient({"X": {"ticker": "X", "status": "finalized", "result": "yes"}})

    check_settlements(client, ledger, mode="paper")

    trades = ledger.get_trade_log(mode="paper")
    assert trades[0]["status"] == "Won"
    assert trades[0]["payout"] == 10.0


def test_closed_but_not_yet_resolved_stays_open(tmp_path):
    ledger = Ledger(db_path=tmp_path / "test_ledger.db")
    ledger.record_trade_open(mode="paper", ticker="X", event_ticker="X-EVENT",
                              side="bid", price=0.95, count=10, reason="test")
    client = FakeClient({"X": {"ticker": "X", "status": "closed", "result": ""}})

    check_settlements(client, ledger, mode="paper")

    assert len(ledger.get_open_trades(mode="paper")) == 1


def test_buy_no_wins_when_result_is_no(tmp_path):
    ledger = Ledger(db_path=tmp_path / "test_ledger.db")
    ledger.record_trade_open(mode="paper", ticker="X", event_ticker="X-EVENT",
                              side="ask", price=0.97, count=10, reason="test")
    client = FakeClient({"X": {"ticker": "X", "status": "finalized", "result": "no"}})

    check_settlements(client, ledger, mode="paper")

    trades = ledger.get_trade_log(mode="paper")
    assert trades[0]["status"] == "Won"
    assert trades[0]["payout"] == 10.0


def test_loses_when_result_does_not_match_side(tmp_path):
    ledger = Ledger(db_path=tmp_path / "test_ledger.db")
    ledger.record_trade_open(mode="paper", ticker="X", event_ticker="X-EVENT",
                              side="bid", price=0.95, count=10, reason="test")
    client = FakeClient({"X": {"ticker": "X", "status": "finalized", "result": "no"}})

    check_settlements(client, ledger, mode="paper")

    trades = ledger.get_trade_log(mode="paper")
    assert trades[0]["status"] == "Lost"
    assert trades[0]["payout"] == 0.0
