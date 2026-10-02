import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from kalshi_bot.engine.paper import PaperBroker
from kalshi_bot.ledger import Ledger
from kalshi_bot.strategy.base import TradeSignal


def make_broker(tmp_path, seed_cash=100.0) -> tuple[PaperBroker, Ledger]:
    ledger = Ledger(db_path=tmp_path / "test_ledger.db")
    broker = PaperBroker(ledger, default_seed_cash=seed_cash)
    return broker, ledger


def test_seeds_cash_once_as_a_paper_deposit(tmp_path):
    broker, ledger = make_broker(tmp_path, seed_cash=100.0)
    assert broker.get_account_snapshot().cash_dollars == 100.0
    assert len(ledger.get_deposits(mode="paper")) == 1

    # A second PaperBroker instance (e.g. after a restart) must not re-seed
    # or drift the anchor even if called with a different default.
    broker2 = PaperBroker(ledger, default_seed_cash=9999.0)
    assert broker2.get_account_snapshot().cash_dollars == 100.0
    assert len(ledger.get_deposits(mode="paper")) == 1


def test_open_trade_reduces_cash_and_counts_as_exposure(tmp_path):
    broker, ledger = make_broker(tmp_path, seed_cash=100.0)
    signal = TradeSignal(ticker="X", title="X Market?", event_ticker="X-EVENT", side="bid",
                          limit_price=0.95, true_price=0.95, reason="test")
    broker.execute(signal)  # no-op besides logging; ledger write mimics what Runner does
    ledger.record_trade_open(mode="paper", ticker="X", event_ticker="X-EVENT",
                              side="bid", price=0.95, count=10, reason="test")

    account = broker.get_account_snapshot()
    assert account.cash_dollars == pytest.approx(100.0 - 9.5)
    assert account.equity_dollars == pytest.approx(100.0)  # cash + open cost == unchanged
    assert broker.open_positions_count() == 1
    assert broker.total_exposure_dollars() == pytest.approx(9.5)


def test_settlement_credits_payout_back_to_cash(tmp_path):
    broker, ledger = make_broker(tmp_path, seed_cash=100.0)
    trade_id = ledger.record_trade_open(mode="paper", ticker="X", event_ticker="X-EVENT",
                                         side="bid", price=0.95, count=10, reason="test")
    ledger.record_settlement(trade_id, "Won", payout=10.0)

    account = broker.get_account_snapshot()
    assert account.cash_dollars == pytest.approx(100.0 - 9.5 + 10.0)
    assert broker.open_positions_count() == 0
    assert broker.total_exposure_dollars() == 0.0


def test_buy_no_trade_costs_the_true_no_price_not_the_order_price(tmp_path):
    # side='ask' sends limit_price=yes_bid to the API, but the real cost of
    # buying NO is true_price (no_ask) -- this is the bug that caused wildly
    # oversized 'buy no' trades before true_price existed.
    broker, ledger = make_broker(tmp_path, seed_cash=100.0)
    ledger.record_trade_open(mode="paper", ticker="X", event_ticker="X-EVENT",
                              side="ask", price=0.99, count=10, reason="test")  # true_price=0.99, not yes_bid=0.01
    assert broker.total_exposure_dollars() == pytest.approx(9.9)
