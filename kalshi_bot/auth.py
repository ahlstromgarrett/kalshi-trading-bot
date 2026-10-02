from __future__ import annotations

import base64
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa


class KalshiSigner:
    """Signs REST requests per Kalshi's KALSHI-ACCESS-* header scheme.

    String signed is f"{timestamp_ms}{METHOD}{path}" (path excludes query params).
    RSA keys sign with PSS/SHA-256; Ed25519 keys sign the message directly.
    """

    def __init__(self, api_key_id: str, private_key_path: Path):
        self.api_key_id = api_key_id
        self._private_key = self._load_key(private_key_path)

    @staticmethod
    def _load_key(path: Path):
        data = path.read_bytes()
        return serialization.load_pem_private_key(data, password=None)

    def _sign(self, message: str) -> str:
        msg_bytes = message.encode("utf-8")
        if isinstance(self._private_key, ed25519.Ed25519PrivateKey):
            signature = self._private_key.sign(msg_bytes)
        elif isinstance(self._private_key, rsa.RSAPrivateKey):
            signature = self._private_key.sign(
                msg_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH,
                ),
                hashes.SHA256(),
            )
        else:
            raise TypeError(f"Unsupported private key type: {type(self._private_key)}")
        return base64.b64encode(signature).decode("utf-8")

    def headers(self, method: str, path: str) -> dict:
        """path must be the path only, e.g. /trade-api/v2/portfolio/balance (no query string)."""
        timestamp_ms = str(int(time.time() * 1000))
        message = f"{timestamp_ms}{method.upper()}{path}"
        signature = self._sign(message)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }
