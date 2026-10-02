import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_bot.sizing import size_contracts


def test_sizes_to_position_fraction_of_equity():
    # 3% of $1000 equity = $30 target, at $0.95/contract -> 31 contracts
    count = size_contracts(equity_dollars=1000, cash_dollars=1000, position_fraction=0.03,
                            max_position_fraction=0.08, price=0.95)
    assert count == 31


def test_caps_at_max_position_fraction():
    count = size_contracts(equity_dollars=1000, cash_dollars=1000, position_fraction=0.50,
                            max_position_fraction=0.08, price=0.95)
    assert count == int((1000 * 0.08) // 0.95)


def test_never_exceeds_available_cash():
    count = size_contracts(equity_dollars=1000, cash_dollars=5, position_fraction=0.03,
                            max_position_fraction=0.08, price=0.95)
    assert count == 5  # floor(5 / 0.95)


def test_returns_zero_when_cant_afford_one_contract():
    count = size_contracts(equity_dollars=1000, cash_dollars=0.50, position_fraction=0.03,
                            max_position_fraction=0.08, price=0.95)
    assert count == 0
