import httpx

from app.services.artic_client import ArtInstituteClient, ArtInstituteServiceError


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_cache_hit_skips_second_http_call(monkeypatch):
    monkeypatch.setenv("ARTIC_CACHE_TTL_SECONDS", "300")
    calls = {"count": 0}

    def fake_get(url, params, timeout):  # noqa: ANN001
        calls["count"] += 1
        return DummyResponse(200, {"data": {"id": 111, "title": "Cached Title"}})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = ArtInstituteClient()

    first = client.place_exists(111)
    second = client.place_exists(111)

    assert first == (True, "Cached Title")
    assert second == (True, "Cached Title")
    assert calls["count"] == 1


def test_cache_expiry_triggers_new_http_call(monkeypatch):
    monkeypatch.setenv("ARTIC_CACHE_TTL_SECONDS", "0")
    calls = {"count": 0}

    def fake_get(url, params, timeout):  # noqa: ANN001
        calls["count"] += 1
        return DummyResponse(200, {"data": {"id": 111, "title": "No Cache"}})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = ArtInstituteClient()

    client.place_exists(111)
    client.place_exists(111)

    assert calls["count"] == 2


def test_not_found_is_cached(monkeypatch):
    monkeypatch.setenv("ARTIC_CACHE_TTL_SECONDS", "300")
    calls = {"count": 0}

    def fake_get(url, params, timeout):  # noqa: ANN001
        calls["count"] += 1
        return DummyResponse(404, {})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = ArtInstituteClient()

    first = client.place_exists(999999)
    second = client.place_exists(999999)

    assert first == (False, None)
    assert second == (False, None)
    assert calls["count"] == 1


def test_upstream_errors_are_not_cached(monkeypatch):
    monkeypatch.setenv("ARTIC_CACHE_TTL_SECONDS", "300")
    calls = {"count": 0}

    def fake_get(url, params, timeout):  # noqa: ANN001
        calls["count"] += 1
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = ArtInstituteClient()

    for _ in range(2):
        try:
            client.place_exists(111)
        except ArtInstituteServiceError:
            pass

    assert calls["count"] == 2
