from __future__ import annotations

import json
import os
import time

import pytest
import requests

from apex_fpl.data.http import CachedHttp


class _JsonResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_forced_refresh_prefers_live_response_and_updates_cache(tmp_path, monkeypatch):
    client = CachedHttp(tmp_path, stale_if_error_seconds=3600)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _JsonResponse({"source": "live"}))

    payload = client.get_json("https://example.test/live", "official", force=True)

    assert payload == {"source": "live"}
    assert json.loads(client._path("official.json").read_text()) == {"source": "live"}


def test_forced_refresh_uses_recent_cache_on_transport_failure(tmp_path, monkeypatch):
    client = CachedHttp(tmp_path, ttl_seconds=60, stale_if_error_seconds=3600)
    cache_file = client._path("official.json")
    cache_file.write_text(json.dumps({"source": "cache"}))
    recent = time.time() - 1800
    os.utime(cache_file, (recent, recent))

    def fail(*args, **kwargs):
        raise requests.ConnectionError("temporary DNS failure")

    monkeypatch.setattr(requests, "get", fail)

    assert client.get_json("https://example.test/live", "official", force=True) == {
        "source": "cache"
    }


def test_forced_refresh_fails_closed_when_cache_is_too_old(tmp_path, monkeypatch):
    client = CachedHttp(tmp_path, ttl_seconds=60, stale_if_error_seconds=3600)
    cache_file = client._path("official.json")
    cache_file.write_text(json.dumps({"source": "stale-cache"}))
    stale = time.time() - 7200
    os.utime(cache_file, (stale, stale))

    def fail(*args, **kwargs):
        raise requests.ConnectionError("temporary DNS failure")

    monkeypatch.setattr(requests, "get", fail)

    with pytest.raises(requests.ConnectionError):
        client.get_json("https://example.test/live", "official", force=True)
