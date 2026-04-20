from app.dependencies import get_artic_client
from app.services.artic_client import ArtInstituteServiceError
from main import app


def test_create_project(client):
    response = client.post(
        "/projects",
        json={"name": "Italy Trip", "description": "Rome and Florence", "start_date": "2026-06-01"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Italy Trip"
    assert payload["description"] == "Rome and Florence"
    assert payload["start_date"] == "2026-06-01"
    assert payload["places"] == []
    assert payload["is_completed"] is False


def test_create_project_with_places(client):
    response = client.post(
        "/projects",
        json={
            "name": "Museum Tour",
            "places": [
                {"external_id": 111, "notes": "Morning visit"},
                {"external_id": 222, "notes": "Buy tickets online"},
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload["places"]) == 2
    assert payload["places"][0]["external_id"] == 111
    assert payload["places"][1]["external_id"] == 222


def test_reject_duplicate_places_in_create_request(client):
    response = client.post(
        "/projects",
        json={"name": "Duplicate IDs", "places": [{"external_id": 111}, {"external_id": 111}]},
    )
    assert response.status_code == 409


def test_reject_invalid_external_place_on_create(client):
    response = client.post(
        "/projects",
        json={"name": "Invalid place", "places": [{"external_id": 999999}]},
    )
    assert response.status_code == 400


def test_list_get_patch_and_delete_project(client):
    create = client.post("/projects", json={"name": "Edit me"})
    project_id = create.json()["id"]

    list_response = client.get("/projects")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Edit me"

    patch_response = client.patch(f"/projects/{project_id}", json={"name": "Edited"})
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Edited"

    delete_response = client.delete(f"/projects/{project_id}")
    assert delete_response.status_code == 204

    get_after_delete = client.get(f"/projects/{project_id}")
    assert get_after_delete.status_code == 404


def test_create_project_returns_502_when_artic_is_unavailable(client):
    class FailingClient:
        def place_exists(self, external_id: int):
            raise ArtInstituteServiceError("upstream down")

    app.dependency_overrides[get_artic_client] = lambda: FailingClient()
    try:
        response = client.post(
            "/projects",
            json={"name": "Trip", "places": [{"external_id": 111}]},
        )
        assert response.status_code == 502
    finally:
        app.dependency_overrides.pop(get_artic_client, None)
