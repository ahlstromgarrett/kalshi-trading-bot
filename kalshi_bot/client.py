from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from .auth import KalshiSigner
from .config import Settings

logger = logging.getLogger(__name__)

API_PREFIX = "/trade-api/v2"


class KalshiApiError(RuntimeError):
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Kalshi API error {status_code}: {body}")


class KalshiClient:
    """Thin REST wrapper over Kalshi's trade API v2.

    Every authenticated call signs {timestamp_ms}{METHOD}{/trade-api/v2/path}
    per KalshiSigner. See https://docs.kalshi.com for the source of truth --
    endpoints here were captured from live docs in Sept 2026 and may drift.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.signer = KalshiSigner(settings.api_key_id, settings.private_key_path)
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, params: Optional[dict] = None,
                 json_body: Optional[dict] = None) -> Any:
        url = f"{self.settings.base_url}{endpoint}"
        sign_path = f"{API_PREFIX}{endpoint}"
        headers = self.signer.headers(method, sign_path)
        headers["Content-Type"] = "application/json"

        resp = self.session.request(
            method, url, params=params, json=json_body, headers=headers, timeout=15
        )
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            raise KalshiApiError(resp.status_code, body)
        if not resp.content:
            return {}
        return resp.json()

    # ---- Market data ----

    def get_markets(self, **params) -> dict:
        return self._request("GET", "/markets", params=params)

    def get_market(self, ticker: str) -> dict:
        return self._request("GET", f"/markets/{ticker}")

    def get_orderbook(self, ticker: str, depth: Optional[int] = None) -> dict:
        params = {"depth": depth} if depth is not None else None
        return self._request("GET", f"/markets/{ticker}/orderbook", params=params)

    def get_event(self, event_ticker: str) -> dict:
        return self._request("GET", f"/events/{event_ticker}")

    # ---- Portfolio (read) ----

    def get_balance(self) -> dict:
        return self._request("GET", "/portfolio/balance")

    def get_positions(self, **params) -> dict:
        return self._request("GET", "/portfolio/positions", params=params)

    def get_orders(self, **params) -> dict:
        return self._request("GET", "/portfolio/orders", params=params)

    def get_fills(self, **params) -> dict:
        return self._request("GET", "/portfolio/fills", params=params)

    # ---- Orders (write) ----

    def create_order(self, ticker: str, side: str, count: str, price: str,
                      time_in_force: str = "immediate_or_cancel",
                      self_trade_prevention_type: str = "taker_at_cross",
                      client_order_id: Optional[str] = None) -> dict:
        """side: 'bid' or 'ask'. count/price are fixed-point decimal strings, e.g. '10.00' / '0.55'."""
        body = {
            "ticker": ticker,
            "side": side,
            "count": count,
            "price": price,
            "time_in_force": time_in_force,
            "self_trade_prevention_type": self_trade_prevention_type,
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/portfolio/events/orders", json_body=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")
