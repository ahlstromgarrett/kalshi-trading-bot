from __future__ import annotations

import math


def size_contracts(equity_dollars: float, cash_dollars: float, position_fraction: float,
                    max_position_fraction: float, price: float, min_contracts: int = 1) -> int:
    """How many whole contracts to buy for a trade, given a target % of equity.

    Sizes off equity (so limits track true account size) but never proposes
    spending more than is actually sitting in cash. Returns 0 if the target
    stake can't afford even one contract -- callers should skip the trade.
    """
    if price <= 0:
        return 0

    fraction = min(position_fraction, max_position_fraction)
    target_dollars = min(equity_dollars * fraction, cash_dollars)
    count = math.floor(target_dollars / price)
    return count if count >= min_contracts else 0
