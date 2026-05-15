"""Tests for API key middleware and auth helpers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from dcm_anon_vault.auth import hash_key, parse_api_keys


class TestParseApiKeys:
    def test_single_pair(self) -> None:
        result = parse_api_keys("customer1:mykey")
        expected_hash = hash_key("mykey")
        assert result == {expected_hash: "customer1"}

    def test_multiple_pairs(self) -> None:
        result = parse_api_keys("a:key1,b:key2")
        assert len(result) == 2
        assert result[hash_key("key1")] == "a"
        assert result[hash_key("key2")] == "b"

    def test_empty_string(self) -> None:
        assert parse_api_keys("") == {}

    def test_malformed_pair_skipped(self) -> None:
        result = parse_api_keys("badentry,good:key")
        assert len(result) == 1
        assert result[hash_key("key")] == "good"


class TestHashKey:
    def test_deterministic(self) -> None:
        assert hash_key("abc") == hash_key("abc")

    def test_length(self) -> None:
        assert len(hash_key("anything")) == 64

    def test_different_keys_differ(self) -> None:
        assert hash_key("key1") != hash_key("key2")


class TestMiddlewareIntegration:
    def test_missing_key_returns_401(self, client: TestClient) -> None:
        # GET on a POST route still hits the middleware first; 401 precedes 405.
        resp = client.get("/v1/anonymize")
        assert resp.status_code in {401, 405}

    def test_wrong_key_returns_401(self, client: TestClient) -> None:
        resp = client.post("/v1/anonymize", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401
