from __future__ import annotations

import argparse
import logging

from kalshi_bot.client import KalshiClient
from kalshi_bot.config import Settings
from kalshi_bot.engine.live import LiveBroker
from kalshi_bot.engine.paper import PaperBroker
from kalshi_bot.engine.runner import Runner
from kalshi_bot.ledger import Ledger
from kalshi_bot.logging_setup import configure_logging
from kalshi_bot.risk import RiskManager
from kalshi_bot.strategy.manual_replica import ManualReplicaStrategy

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi manual-strategy trading bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper",
                         help="paper = simulated fills, no real orders. live = real orders on KALSHI_ENV.")
    parser.add_argument("--interval", type=float, default=30.0, help="Seconds between polls")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit")
    args = parser.parse_args()

    configure_logging()
    settings = Settings.load()

    client = KalshiClient(settings)
    risk = RiskManager(settings.risk)
    strategy = ManualReplicaStrategy(settings.strategy)
    ledger = Ledger()

    if args.mode == "live":
        if not settings.is_live:
            logger.warning(
                "--mode live requested but KALSHI_ENV=%s (not 'prod'). "
                "Orders will go to the demo sandbox, not your real account.",
                settings.env,
            )
        broker = LiveBroker(client)
        logger.warning("LIVE MODE: real orders will be placed against %s", settings.base_url)
    else:
        default_seed_cash = 1000.0
        try:
            default_seed_cash = client.get_balance().get("balance", 100000) / 100.0
        except Exception:
            logger.warning("Could not fetch live balance to seed paper cash, defaulting to $1000", exc_info=True)
        broker = PaperBroker(ledger, default_seed_cash=default_seed_cash)
        logger.info(
            "Paper mode: no real orders will be placed. Seed cash: $%.2f (only recorded once, "
            "on the very first paper run -- later restarts reuse the ledger's existing seed).",
            default_seed_cash,
        )

    runner = Runner(client, strategy, risk, broker, settings.strategy.max_hours_to_close,
                     ledger, args.mode)

    if args.once:
        runner.run_once()
    else:
        runner.run_forever(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
