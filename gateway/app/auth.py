"""The gateway's token check (pattern 10): verify once at the edge with the user service's public key."""
from shop_common.auth import TokenVerifier

from . import config

TOKENS = TokenVerifier(lambda: config.url_for("user"))
