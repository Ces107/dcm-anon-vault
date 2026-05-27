"""OIDC (Bearer JWT) authentication — alternative to API-key auth.

Protocol + factory pattern. The concrete :class:`JwksOidcAuthenticator`
fetches a JWKS document from ``<OIDC_DISCOVERY_URL>`` (RFC 8414 metadata
endpoint), caches the keys, and validates an incoming ``Authorization:
Bearer <jwt>`` header using RS256 / ES256.

If ``OIDC_DISCOVERY_URL`` is unset, :func:`oidc_authenticator` returns
``None`` and the existing API-key path remains the sole auth method.

This is designed to land in two stages:

1. **Today (0.2.x)** — bearer path is wired but disabled by default; one
   reference unit test mocks the JWKS endpoint. Production deployments
   that need OIDC should pin a specific identity provider and validate
   end-to-end on staging before enabling.
2. **Later (0.3.x)** — multi-IdP discovery, JIT customer provisioning
   from ``sub`` claim, group-to-tier mapping. Tracked under the
   ``oidc-prod`` issue.

We deliberately stop short of a full SAML implementation (heavy dep,
not commonly demanded by EU healthcare buyers who already have
Keycloak/Azure-AD OIDC). Enterprise SAML is a paid integration
("ask us about SAML" — interface stub in :class:`OIDCAuthenticator`).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class OIDCPrincipal:
    """Result of a successful JWT validation."""

    subject: str  # ``sub`` claim, used as customer_id_string
    tenant: str  # ``tenant`` claim or fallback to subject
    raw_claims: dict[str, Any] = field(default_factory=dict)


class OIDCError(Exception):
    """Raised when an OIDC token fails validation."""


@runtime_checkable
class OIDCAuthenticator(Protocol):
    """Validates a bearer JWT and returns an :class:`OIDCPrincipal`."""

    def validate(self, token: str) -> OIDCPrincipal: ...


class JwksOidcAuthenticator:
    """Validates JWTs against a JWKS endpoint discovered via OIDC metadata.

    Cache is in-process with TTL ``cache_ttl`` (default 5 min). The
    constructor does **not** fetch — discovery happens lazily on first
    ``validate()`` so import remains side-effect free.
    """

    def __init__(
        self,
        discovery_url: str,
        *,
        audience: str | None = None,
        issuer: str | None = None,
        cache_ttl: int = 300,
        http_get: object | None = None,
    ) -> None:
        self._discovery_url = discovery_url
        self._audience = audience or os.environ.get("OIDC_AUDIENCE")
        self._issuer = issuer or os.environ.get("OIDC_ISSUER")
        self._cache_ttl = cache_ttl
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at: float = 0.0
        # http_get is an injectable callable for tests:
        # ``(url: str) -> dict`` returning the JSON body.
        self._http_get = http_get

    def _fetch_json(self, url: str) -> dict[str, Any]:
        if self._http_get is not None:
            result = self._http_get(url)  # type: ignore[operator]
            if isinstance(result, dict):
                return result
            raise OIDCError(f"http_get returned non-dict for {url}")
        try:
            # urlopen is fine here: the URL is the operator-configured
            # OIDC_DISCOVERY_URL, not attacker-controlled.
            with urllib.request.urlopen(url, timeout=5) as resp:  # nosec B310
                raw = resp.read()
                return dict(json.loads(raw))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise OIDCError(f"discovery fetch failed: {exc}") from exc

    def _load_jwks(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._jwks is not None and (now - self._jwks_fetched_at) < self._cache_ttl:
            return self._jwks
        meta = self._fetch_json(self._discovery_url)
        jwks_uri = meta.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            raise OIDCError("OIDC metadata missing jwks_uri")
        jwks = self._fetch_json(jwks_uri)
        if not isinstance(jwks.get("keys"), list):
            raise OIDCError("JWKS document missing 'keys'")
        self._jwks = jwks
        self._jwks_fetched_at = now
        return jwks

    def validate(self, token: str) -> OIDCPrincipal:
        """Validate ``token`` and return the principal, else raise OIDCError."""
        try:
            from jose import jwt as jose_jwt
        except ImportError as exc:
            raise OIDCError("python-jose not installed") from exc

        jwks = self._load_jwks()
        try:
            unverified = jose_jwt.get_unverified_header(token)
            kid = unverified.get("kid")
        except Exception as exc:
            raise OIDCError(f"invalid JWT header: {exc}") from exc

        key = None
        for jwk in jwks["keys"]:
            if jwk.get("kid") == kid:
                key = jwk
                break
        if key is None and jwks["keys"]:
            # Fall back to first key if no kid match (single-key IdPs).
            key = jwks["keys"][0]
        if key is None:
            raise OIDCError(f"no JWKS key for kid={kid!r}")

        try:
            claims: dict[str, Any] = jose_jwt.decode(
                token,
                key,
                algorithms=[str(key.get("alg") or "RS256")],
                audience=self._audience,
                issuer=self._issuer,
                options={"verify_aud": self._audience is not None,
                         "verify_iss": self._issuer is not None},
            )
        except Exception as exc:
            raise OIDCError(f"JWT validation failed: {exc}") from exc

        sub = str(claims.get("sub") or "")
        if not sub:
            raise OIDCError("JWT missing 'sub' claim")
        tenant = str(claims.get("tenant") or sub)
        return OIDCPrincipal(subject=sub, tenant=tenant, raw_claims=claims)


_authenticator: OIDCAuthenticator | None = None
_authenticator_url: str | None = None


def oidc_authenticator() -> OIDCAuthenticator | None:
    """Factory: returns the configured authenticator, or None if disabled.

    Re-evaluates on each call so tests can mutate ``OIDC_DISCOVERY_URL``
    via :class:`monkeypatch`. If a test has injected an authenticator
    via :func:`set_authenticator_for_test`, it is returned regardless of
    the env var (the test seam wins).
    """
    global _authenticator, _authenticator_url
    if _authenticator_url == "TEST" and _authenticator is not None:
        return _authenticator
    discovery_url = os.environ.get("OIDC_DISCOVERY_URL", "").strip()
    if not discovery_url:
        _authenticator = None
        _authenticator_url = None
        return None
    if _authenticator is None or _authenticator_url != discovery_url:
        _authenticator = JwksOidcAuthenticator(discovery_url)
        _authenticator_url = discovery_url
    return _authenticator


def set_authenticator_for_test(auth: OIDCAuthenticator | None) -> None:
    """Test-only seam to inject a mock authenticator."""
    global _authenticator, _authenticator_url
    _authenticator = auth
    _authenticator_url = "TEST" if auth is not None else None
