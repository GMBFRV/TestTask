from app.dependencies import get_artic_client
from app.services.artic_client import ArtInstituteServiceError
from main import app


def test_add_and_get_place(client, auth_headers):
    project = client.post("/projects", json={"name": "Project"}, headers=auth_headers).json()
    project_id = project["id"]

    create_place = client.post(
        f"/projects/{project_id}/places",
        json={"external_id": 111, "notes": "Must see"},
        headers=auth_headers,
    )
    assert create_place.status_code == 201
    place = create_place.json()
    assert place["external_id"] == 111
    assert place["notes"] == "Must see"

    get_place = client.get(f"/projects/{project_id}/places/{place['id']}")
    assert get_place.status_code == 200
    assert get_place.json()["external_id"] == 111


def test_reject_duplicate_external_place(client, auth_headers):
    project_id = client.post("/projects", json={"name": "Project"}, headers=auth_headers).json()["id"]
    first = client.post(f"/projects/{project_id}/places", json={"external_id": 111}, headers=auth_headers)
    assert first.status_code == 201

    duplicate = client.post(f"/projects/{project_id}/places", json={"external_id": 111}, headers=auth_headers)
    assert duplicate.status_code == 409


def test_max_10_places_rule(client, auth_headers):
    project_id = client.post("/projects", json={"name": "Project"}, headers=auth_headers).json()["id"]
    for external_id in [111, 222, 333, 444, 555, 666, 777, 888, 999, 1000]:
        response = client.post(f"/projects/{project_id}/places", json={"external_id": external_id}, headers=auth_headers)
        assert response.status_code == 201

    overflow = client.post(f"/projects/{project_id}/places", json={"external_id": 1001}, headers=auth_headers)
    assert overflow.status_code == 400


def test_notes_and_visited_updates_and_completion(client, auth_headers):
    response = client.post(
        "/projects",
        json={"name": "Trip", "places": [{"external_id": 111}, {"external_id": 222}]},
        headers=auth_headers,
    )
    project = response.json()
    project_id = project["id"]
    place_1 = project["places"][0]["id"]
    place_2 = project["places"][1]["id"]

    update_notes = client.patch(
        f"/projects/{project_id}/places/{place_1}", json={"notes": "Updated note"}, headers=auth_headers
    )
    assert update_notes.status_code == 200
    assert update_notes.json()["notes"] == "Updated note"

    visit_first = client.patch(f"/projects/{project_id}/places/{place_1}", json={"is_visited": True}, headers=auth_headers)
    assert visit_first.status_code == 200
    still_not_completed = client.get(f"/projects/{project_id}")
    assert still_not_completed.json()["is_completed"] is False

    visit_second = client.patch(
        f"/projects/{project_id}/places/{place_2}", json={"is_visited": True}, headers=auth_headers
    )
    assert visit_second.status_code == 200
    now_completed = client.get(f"/projects/{project_id}")
    assert now_completed.json()["is_completed"] is True


def test_delete_project_blocked_if_any_place_visited(client, auth_headers):
    project_id = client.post("/projects", json={"name": "Project"}, headers=auth_headers).json()["id"]
    place = client.post(f"/projects/{project_id}/places", json={"external_id": 111}, headers=auth_headers).json()

    visited = client.patch(
        f"/projects/{project_id}/places/{place['id']}", json={"is_visited": True}, headers=auth_headers
    )
    assert visited.status_code == 200

    delete_response = client.delete(f"/projects/{project_id}", headers=auth_headers)
    assert delete_response.status_code == 409


def test_add_place_returns_502_when_artic_is_unavailable(client, auth_headers):
    class FailingClient:
        def place_exists(self, external_id: int):
            raise ArtInstituteServiceError("upstream down")

    app.dependency_overrides[get_artic_client] = lambda: FailingClient()
    try:
        project_id = client.post("/projects", json={"name": "Project"}, headers=auth_headers).json()["id"]
        response = client.post(f"/projects/{project_id}/places", json={"external_id": 111}, headers=auth_headers)
        assert response.status_code == 502
    finally:
        app.dependency_overrides.pop(get_artic_client, None)


def test_list_places_supports_pagination_and_filters(client, auth_headers):
    project_id = client.post("/projects", json={"name": "Project"}, headers=auth_headers).json()["id"]
    first = client.post(f"/projects/{project_id}/places", json={"external_id": 111}, headers=auth_headers).json()
    second = client.post(f"/projects/{project_id}/places", json={"external_id": 222}, headers=auth_headers).json()
    client.post(f"/projects/{project_id}/places", json={"external_id": 333}, headers=auth_headers)

    client.patch(f"/projects/{project_id}/places/{second['id']}", json={"is_visited": True}, headers=auth_headers)

    page_1 = client.get(f"/projects/{project_id}/places?page=1&page_size=2")
    assert page_1.status_code == 200
    page_1_payload = page_1.json()
    assert page_1_payload["total"] == 3
    assert page_1_payload["page"] == 1
    assert page_1_payload["page_size"] == 2
    assert len(page_1_payload["items"]) == 2

    page_2 = client.get(f"/projects/{project_id}/places?page=2&page_size=2")
    assert page_2.status_code == 200
    assert len(page_2.json()["items"]) == 1

    visited_filter = client.get(f"/projects/{project_id}/places?is_visited=true")
    assert visited_filter.status_code == 200
    visited_payload = visited_filter.json()
    assert visited_payload["total"] == 1
    assert visited_payload["items"][0]["id"] == second["id"]

    search_filter = client.get(f"/projects/{project_id}/places?q=Artwork 111")
    assert search_filter.status_code == 200
    search_payload = search_filter.json()
    assert search_payload["total"] == 1
    assert search_payload["items"][0]["id"] == first["id"]


def test_mutating_place_endpoints_require_auth(client, auth_headers):
    project = client.post("/projects", json={"name": "AuthProject"}, headers=auth_headers).json()
    project_id = project["id"]

    add_no_auth = client.post(f"/projects/{project_id}/places", json={"external_id": 111})
    assert add_no_auth.status_code == 401

    add_ok = client.post(f"/projects/{project_id}/places", json={"external_id": 111}, headers=auth_headers)
    assert add_ok.status_code == 201
    place_id = add_ok.json()["id"]

    patch_no_auth = client.patch(f"/projects/{project_id}/places/{place_id}", json={"notes": "blocked"})
    assert patch_no_auth.status_code == 401

    get_without_auth = client.get(f"/projects/{project_id}/places/{place_id}")
    assert get_without_auth.status_code == 200
