import os
import time
import httpx


class ArtInstituteServiceError(Exception):
    pass


class ArtInstituteClient:
    BASE_URL = "https://api.artic.edu/api/v1"

    def __init__(self) -> None:
        ttl_seconds = os.getenv("ARTIC_CACHE_TTL_SECONDS", "300")
        try:
            parsed_ttl = int(ttl_seconds)
        except ValueError:
            parsed_ttl = 300
        self.cache_ttl_seconds = max(0, parsed_ttl)
        self._cache: dict[int, tuple[bool, str | None, float]] = {}

    def _get_cached(self, external_id: int) -> tuple[bool, str | None] | None:
        cache_entry = self._cache.get(external_id)
        if cache_entry is None:
            return None

        exists, title, expires_at = cache_entry
        if time.time() >= expires_at:
            self._cache.pop(external_id, None)
            return None
        return exists, title

    def _set_cached(self, external_id: int, exists: bool, title: str | None) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        expires_at = time.time() + self.cache_ttl_seconds
        self._cache[external_id] = (exists, title, expires_at)

    def place_exists(self, external_id: int) -> tuple[bool, str | None]:
        cached = self._get_cached(external_id)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/artworks/{external_id}"
        params = {"fields": "id,title"}
        try:
            response = httpx.get(url, params=params, timeout=10.0)
        except httpx.HTTPError as exc:
            raise ArtInstituteServiceError("Could not reach Art Institute API.") from exc

        if response.status_code == 404:
            result = (False, None)
            self._set_cached(external_id, *result)
            return result
        if response.status_code >= 400:
            raise ArtInstituteServiceError("Art Institute API returned an unexpected error.")

        payload = response.json()
        data = payload.get("data")
        if not data:
            result = (False, None)
            self._set_cached(external_id, *result)
            return result

        result = (True, data.get("title"))
        self._set_cached(external_id, *result)
        return result
