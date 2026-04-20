from app.dependencies import get_artic_client
from app.services.artic_client import ArtInstituteServiceError
from main import app


def test_create_project(client, auth_headers):
    response = client.post(
        "/projects",
        json={"name": "Italy Trip", "description": "Rome and Florence", "start_date": "2026-06-01"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Italy Trip"
    assert payload["description"] == "Rome and Florence"
    assert payload["start_date"] == "2026-06-01"
    assert payload["places"] == []
    assert payload["is_completed"] is False


def test_create_project_with_places(client, auth_headers):
    response = client.post(
        "/projects",
        json={
            "name": "Museum Tour",
            "places": [
                {"external_id": 111, "notes": "Morning visit"},
                {"external_id": 222, "notes": "Buy tickets online"},
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload["places"]) == 2
    assert payload["places"][0]["external_id"] == 111
    assert payload["places"][1]["external_id"] == 222


def test_reject_duplicate_places_in_create_request(client, auth_headers):
    response = client.post(
        "/projects",
        json={"name": "Duplicate IDs", "places": [{"external_id": 111}, {"external_id": 111}]},
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_reject_invalid_external_place_on_create(client, auth_headers):
    response = client.post(
        "/projects",
        json={"name": "Invalid place", "places": [{"external_id": 999999}]},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_list_get_patch_and_delete_project(client, auth_headers):
    create = client.post("/projects", json={"name": "Edit me"}, headers=auth_headers)
    project_id = create.json()["id"]

    list_response = client.get("/projects")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["page"] == 1
    assert list_payload["page_size"] == 10
    assert len(list_payload["items"]) == 1

    get_response = client.get(f"/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Edit me"

    patch_response = client.patch(f"/projects/{project_id}", json={"name": "Edited"}, headers=auth_headers)
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Edited"

    delete_response = client.delete(f"/projects/{project_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_after_delete = client.get(f"/projects/{project_id}")
    assert get_after_delete.status_code == 404


def test_create_project_returns_502_when_artic_is_unavailable(client, auth_headers):
    class FailingClient:
        def place_exists(self, external_id: int):
            raise ArtInstituteServiceError("upstream down")

    app.dependency_overrides[get_artic_client] = lambda: FailingClient()
    try:
        response = client.post(
            "/projects",
            json={"name": "Trip", "places": [{"external_id": 111}]},
            headers=auth_headers,
        )
        assert response.status_code == 502
    finally:
        app.dependency_overrides.pop(get_artic_client, None)


def test_list_projects_supports_pagination_and_filters(client, auth_headers):
    client.post("/projects", json={"name": "Alpha", "start_date": "2026-01-01"}, headers=auth_headers)
    second = client.post("/projects", json={"name": "Beta", "start_date": "2026-02-01"}, headers=auth_headers).json()
    client.post("/projects", json={"name": "Gamma", "start_date": "2026-03-01"}, headers=auth_headers)

    place = client.post(f"/projects/{second['id']}/places", json={"external_id": 111}, headers=auth_headers).json()
    client.patch(f"/projects/{second['id']}/places/{place['id']}", json={"is_visited": True}, headers=auth_headers)

    page_1 = client.get("/projects?page=1&page_size=2")
    assert page_1.status_code == 200
    page_1_payload = page_1.json()
    assert page_1_payload["total"] == 3
    assert len(page_1_payload["items"]) == 2

    page_2 = client.get("/projects?page=2&page_size=2")
    assert page_2.status_code == 200
    assert len(page_2.json()["items"]) == 1

    completed_filter = client.get("/projects?is_completed=true")
    assert completed_filter.status_code == 200
    completed_payload = completed_filter.json()
    assert completed_payload["total"] == 1
    assert completed_payload["items"][0]["name"] == "Beta"

    date_range = client.get("/projects?start_date_from=2026-02-01&start_date_to=2026-03-01")
    assert date_range.status_code == 200
    assert date_range.json()["total"] == 2

    name_search = client.get("/projects?q=alp")
    assert name_search.status_code == 200
    name_search_payload = name_search.json()
    assert name_search_payload["total"] == 1
    assert name_search_payload["items"][0]["name"] == "Alpha"


def test_list_projects_rejects_invalid_date_range(client):
    response = client.get("/projects?start_date_from=2026-03-02&start_date_to=2026-03-01")
    assert response.status_code == 422


def test_mutating_project_endpoints_require_auth(client, auth_headers):
    create_no_auth = client.post("/projects", json={"name": "NoAuth"})
    assert create_no_auth.status_code == 401

    create_ok = client.post("/projects", json={"name": "WithAuth"}, headers=auth_headers)
    assert create_ok.status_code == 201
    project_id = create_ok.json()["id"]

    patch_no_auth = client.patch(f"/projects/{project_id}", json={"name": "Blocked"})
    assert patch_no_auth.status_code == 401

    delete_no_auth = client.delete(f"/projects/{project_id}")
    assert delete_no_auth.status_code == 401
