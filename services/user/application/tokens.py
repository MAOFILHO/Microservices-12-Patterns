"""Signs login tokens (pattern 10). Only the user service holds the private key.

Key source, in order: JWT_PRIVATE_KEY_B64 (base64 PEM, the Azure Container Apps secret set by
provision), JWT_PRIVATE_KEY_PEM, else instance/jwt_private.pem, created on first start. Keeping the key in a file means restarting the service does not log anyone out.
"""
import base64
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shop_common.auth import ALGORITHM, ISSUER

TOKEN_LIFETIME = timedelta(hours=1)
KEY_FILE = Path(__file__).resolve().parents[1] / os.environ.get("JWT_KEY_FILE", "instance/jwt_private.pem")

_private_pem: bytes | None = None


def _private_key_pem() -> bytes:
    global _private_pem
    if _private_pem is None:
        if os.environ.get("JWT_PRIVATE_KEY_B64"):
            _private_pem = base64.b64decode(os.environ["JWT_PRIVATE_KEY_B64"])
        elif os.environ.get("JWT_PRIVATE_KEY_PEM"):
            _private_pem = os.environ["JWT_PRIVATE_KEY_PEM"].encode()
        elif KEY_FILE.exists():
            _private_pem = KEY_FILE.read_bytes()
        else:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            _private_pem = key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
            KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            KEY_FILE.write_bytes(_private_pem)
            KEY_FILE.chmod(0o600)
    return _private_pem


def public_key_pem() -> str:
    key = serialization.load_pem_private_key(_private_key_pem(), password=None)
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def issue(user) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user.id), "username": user.username, "iss": ISSUER, "iat": now, "exp": now + TOKEN_LIFETIME}
    return jwt.encode(claims, _private_key_pem(), algorithm=ALGORITHM)


def decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, public_key_pem(), algorithms=[ALGORITHM], issuer=ISSUER)
    except jwt.InvalidTokenError:
        return None
