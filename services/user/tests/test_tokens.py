"""Pattern 10: login returns a signed token, and the token alone says who is calling."""


def _register_and_login(client, username="bob"):
    client.post("/api/user/create", data={"username": username, "email": f"{username}@example.com", "password": "secret123"})
    return client.post("/api/user/login", data={"username": username, "password": "secret123"}).get_json()


def test_login_returns_a_signed_token_and_stores_nothing(client):
    body = _register_and_login(client)
    assert body["token"].count(".") == 2  # header.claims.signature
    assert body["expires_in"] == 3600


def test_token_identifies_the_user_without_a_session(client):
    token = _register_and_login(client)["token"]
    # A fresh client has no cookies: only the token says who this is.
    fresh = client.application.test_client()
    r = fresh.get("/api/user", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["result"]["username"] == "bob"
    assert "Set-Cookie" not in r.headers


def test_tampered_or_missing_token_is_rejected(client):
    token = _register_and_login(client)["token"]
    assert client.get("/api/user").status_code == 401
    assert client.get("/api/user", headers={"Authorization": f"Bearer {token[:-4]}AAAA"}).status_code == 401


def test_public_key_verifies_the_token(client):
    import jwt

    token = _register_and_login(client)["token"]
    key = client.get("/api/user/public-key").get_json()["public_key_pem"]
    assert jwt.decode(token, key, algorithms=["RS256"], issuer="ms12p-user")["username"] == "bob"


def test_signing_key_can_come_from_the_azure_secret(client, monkeypatch, tmp_path):
    """In Azure, provision passes the key base64-encoded in JWT_PRIVATE_KEY_B64 (a Container Apps
    secret), so every replica and every restart signs with the same key."""
    import base64

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from application import tokens

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    monkeypatch.setenv("JWT_PRIVATE_KEY_B64", base64.b64encode(pem).decode())
    monkeypatch.setattr(tokens, "_private_pem", None)
    monkeypatch.setattr(tokens, "KEY_FILE", tmp_path / "unused.pem")

    token = _register_and_login(client, "carol")["token"]
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert jwt.decode(token, public, algorithms=["RS256"], issuer="ms12p-user")["username"] == "carol"
    assert not (tmp_path / "unused.pem").exists()
