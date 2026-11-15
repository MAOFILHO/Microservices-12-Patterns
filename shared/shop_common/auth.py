"""Stateless login tokens (pattern 10).

The user service signs a short-lived JWT with its private key (RS256). Every other process
verifies it with the public key, which it fetches once from the user service. No process keeps a
session, so any replica can serve any request and a restart logs nobody out.
"""
import json
import threading
import urllib.request
from typing import Callable

import jwt

ALGORITHM = "RS256"
ISSUER = "ms12p-user"
PUBLIC_KEY_PATH = "/api/user/public-key"


def bearer_token(header: str | None) -> str | None:
    """Accepts 'Bearer <jwt>' (or a bare token) from an Authorization header."""
    if not header:
        return None
    token = header.split(" ", 1)[1] if " " in header else header
    return token.strip() or None


class TokenVerifier:
    """Verifies tokens against the user service's public key, fetched lazily and cached.

    user_base_url is a callable so the key is fetched from wherever discovery says the user
    service lives right now.
    """

    def __init__(self, user_base_url: Callable[[], str], timeout: float = 3.0):
        self._user_base_url = user_base_url
        self._timeout = timeout
        self._key: str | None = None
        self._lock = threading.Lock()

    def _public_key(self, refresh: bool = False) -> str | None:
        with self._lock:
            if self._key is None or refresh:
                try:
                    url = f"{self._user_base_url()}{PUBLIC_KEY_PATH}"
                    with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                        self._key = json.load(resp)["public_key_pem"]
                except (OSError, ValueError, KeyError):
                    return self._key  # keep a previously fetched key if the user service is down
            return self._key

    def verify(self, authorization_header: str | None) -> dict | None:
        """Returns the token's claims, or None if it is missing, expired or not signed by us."""
        token = bearer_token(authorization_header)
        if not token:
            return None
        for refresh in (False, True):  # retry once with a fresh key, in case the user service rotated it
            key = self._public_key(refresh=refresh)
            if key is None:
                return None
            try:
                return jwt.decode(token, key, algorithms=[ALGORITHM], issuer=ISSUER)
            except jwt.InvalidSignatureError:
                continue
            except jwt.InvalidTokenError:
                return None
        return None
