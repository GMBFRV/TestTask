import httpx


class ArtInstituteServiceError(Exception):
    pass


class ArtInstituteClient:
    BASE_URL = "https://api.artic.edu/api/v1"

    def place_exists(self, external_id: int) -> tuple[bool, str | None]:
        url = f"{self.BASE_URL}/artworks/{external_id}"
        params = {"fields": "id,title"}
        try:
            response = httpx.get(url, params=params, timeout=10.0)
        except httpx.HTTPError as exc:
            raise ArtInstituteServiceError("Could not reach Art Institute API.") from exc

        if response.status_code == 404:
            return False, None
        if response.status_code >= 400:
            raise ArtInstituteServiceError("Art Institute API returned an unexpected error.")

        payload = response.json()
        data = payload.get("data")
        if not data:
            return False, None
        return True, data.get("title")
