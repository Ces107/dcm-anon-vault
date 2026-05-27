"""Tests for the OIDC Bearer-token authentication stub."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

try:
    from jose import jwt as jose_jwt  # type: ignore[import-not-found]

    HAS_JOSE = True
except ImportError:
    HAS_JOSE = False

from dcm_anon_vault.auth_oidc import (
    JwksOidcAuthenticator,
    OIDCError,
    oidc_authenticator,
)
from tests.conftest import TEST_KEY


def test_authenticator_disabled_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_DISCOVERY_URL", raising=False)
    assert oidc_authenticator() is None


def test_authenticator_enabled_when_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_DISCOVERY_URL", "https://idp.example/.well-known/openid-configuration")
    auth = oidc_authenticator()
    assert auth is not None


@pytest.mark.skipif(not HAS_JOSE, reason="python-jose not installed")
def test_jwks_authenticator_validates_signed_jwt() -> None:
    # Generate an RSA key + JWK for the JWKS endpoint mock.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_numbers = private_key.public_key().public_numbers()

    def _b64(n: int) -> str:
        import base64
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    jwk = {
        "kty": "RSA",
        "kid": "test-key-1",
        "use": "sig",
        "alg": "RS256",
        "n": _b64(public_numbers.n),
        "e": _b64(public_numbers.e),
    }

    fetched: dict[str, Any] = {}

    def http_get(url: str) -> dict[str, Any]:
        fetched[url] = fetched.get(url, 0) + 1
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": "https://idp.example/jwks"}
        if url == "https://idp.example/jwks":
            return {"keys": [jwk]}
        raise AssertionError(f"unexpected url: {url}")

    auth = JwksOidcAuthenticator(
        discovery_url="https://idp.example/.well-known/openid-configuration",
        audience="dcm-anon-vault",
        issuer="https://idp.example/",
        http_get=http_get,
    )

    # Mint a token.
    now = int(time.time())
    claims = {
        "sub": "alice@acme.test",
        "tenant": "acme",
        "iss": "https://idp.example/",
        "aud": "dcm-anon-vault",
        "iat": now,
        "exp": now + 60,
    }
    token = jose_jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-key-1"})

    principal = auth.validate(token)
    assert principal.subject == "alice@acme.test"
    assert principal.tenant == "acme"
    assert principal.raw_claims["aud"] == "dcm-anon-vault"


def test_jwks_authenticator_rejects_invalid_token() -> None:
    def http_get(url: str) -> dict[str, Any]:
        if "openid-configuration" in url:
            return {"jwks_uri": "https://idp.example/jwks"}
        return {"keys": [{"kid": "k", "kty": "RSA", "n": "AA", "e": "AQAB", "alg": "RS256"}]}

    auth = JwksOidcAuthenticator(
        discovery_url="https://idp.example/.well-known/openid-configuration",
        http_get=http_get,
    )
    with pytest.raises(OIDCError):
        auth.validate("not-a-jwt")


class TestOIDCMiddlewareIntegration:
    def test_bearer_token_accepted_when_authenticator_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dcm_anon_vault.auth_oidc import (
            OIDCPrincipal,
            set_authenticator_for_test,
        )

        class _Stub:
            def validate(self, token: str) -> OIDCPrincipal:
                if token == "good-token":
                    return OIDCPrincipal(subject="alice", tenant="acme", raw_claims={})
                raise OIDCError("bad")

        monkeypatch.setenv("OIDC_DISCOVERY_URL", "https://stub/.well-known/openid-configuration")
        set_authenticator_for_test(_Stub())
        try:
            resp = client.get(
                "/v1/usage", headers={"Authorization": "Bearer good-token"}
            )
            assert resp.status_code == 200
        finally:
            set_authenticator_for_test(None)

    def test_invalid_bearer_returns_401(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dcm_anon_vault.auth_oidc import (
            OIDCPrincipal,
            set_authenticator_for_test,
        )

        class _Stub:
            def validate(self, token: str) -> OIDCPrincipal:
                raise OIDCError("bad")

        monkeypatch.setenv("OIDC_DISCOVERY_URL", "https://stub/.well-known/openid-configuration")
        set_authenticator_for_test(_Stub())
        try:
            resp = client.get(
                "/v1/usage", headers={"Authorization": "Bearer evil"}
            )
            assert resp.status_code == 401
        finally:
            set_authenticator_for_test(None)

    def test_api_key_still_works_when_oidc_disabled(self, client: TestClient) -> None:
        resp = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
