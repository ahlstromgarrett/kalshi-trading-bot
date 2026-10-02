from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEMO_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
PROD_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass
class RiskLimits:
    """All fractions are of current account equity, so limits scale with the balance."""
    position_fraction: float = 0.03          # target stake per trade
    max_position_fraction: float = 0.08       # hard ceiling per trade, even if sizing wants more
    max_total_exposure_fraction: float = 0.60  # cap on money committed across all open positions at once
    max_daily_loss_fraction: float = 0.15      # halt new trades for the day past this drawdown from day-start equity
    max_open_positions: int = 25


@dataclass
class StrategyConfig:
    min_probability: float = 0.90     # only trade a side priced at or above this implied probability
    max_probability: float = 0.99     # ...but never at/above this -- no margin left to cover fees or a surprise
    max_hours_to_close: float = 24.0  # only consider markets settling within this window
    min_minutes_to_close: float = 5.0  # skip markets closing too soon to reliably fill/track


@dataclass
class Settings:
    api_key_id: str
    private_key_path: Path
    env: str
    risk: RiskLimits = field(default_factory=RiskLimits)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)

    @property
    def base_url(self) -> str:
        return PROD_BASE_URL if self.env == "prod" else DEMO_BASE_URL

    @property
    def is_live(self) -> bool:
        return self.env == "prod"

    @classmethod
    def load(cls) -> "Settings":
        api_key_id = os.getenv("KALSHI_API_KEY_ID", "")
        key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "")
        env = os.getenv("KALSHI_ENV", "demo").strip().lower()

        if not api_key_id or not key_path:
            raise RuntimeError(
                "KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set "
                "(copy .env.example to .env and fill them in)."
            )
        if env not in ("demo", "prod"):
            raise RuntimeError(f"KALSHI_ENV must be 'demo' or 'prod', got {env!r}")

        resolved_key_path = Path(key_path).expanduser()
        if not resolved_key_path.exists():
            raise RuntimeError(f"Private key file not found: {resolved_key_path}")

        risk = RiskLimits(
            position_fraction=_float_env("POSITION_FRACTION", 0.03),
            max_position_fraction=_float_env("MAX_POSITION_FRACTION", 0.08),
            max_total_exposure_fraction=_float_env("MAX_TOTAL_EXPOSURE_FRACTION", 0.60),
            max_daily_loss_fraction=_float_env("MAX_DAILY_LOSS_FRACTION", 0.15),
            max_open_positions=_int_env("MAX_OPEN_POSITIONS", 25),
        )
        strategy = StrategyConfig(
            min_probability=_float_env("MIN_PROBABILITY", 0.90),
            max_probability=_float_env("MAX_PROBABILITY", 0.99),
            max_hours_to_close=_float_env("MAX_HOURS_TO_CLOSE", 24.0),
            min_minutes_to_close=_float_env("MIN_MINUTES_TO_CLOSE", 5.0),
        )

        return cls(
            api_key_id=api_key_id,
            private_key_path=resolved_key_path,
            env=env,
            risk=risk,
            strategy=strategy,
        )
