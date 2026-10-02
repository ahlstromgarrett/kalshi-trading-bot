"""Sanity check: confirms your API key + private key can authenticate.
Only makes a read-only balance call -- places no orders.

Usage: python scripts/check_auth.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_bot.client import KalshiClient
from kalshi_bot.config import Settings


def main() -> None:
    settings = Settings.load()
    client = KalshiClient(settings)
    print(f"Connecting to {settings.base_url} ...")
    balance = client.get_balance()
    print("Auth OK. Balance response:")
    print(balance)


if __name__ == "__main__":
    main()
