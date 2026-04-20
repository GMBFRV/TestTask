from app.dependencies import get_artic_client
from app.services.artic_client import ArtInstituteServiceError
from main import app


def test_add_and_get_place(client):
    project = client.post("/projects", json={"name": "Project"}).json()
    project_id = project["id"]

    create_place = client.post(
        f"/projects/{project_id}/places",
        json={"external_id": 111, "notes": "Must see"},
    )
    assert create_place.status_code == 201
    place = create_place.json()
    assert place["external_id"] == 111
    assert place["notes"] == "Must see"

    get_place = client.get(f"/projects/{project_id}/places/{place['id']}")
    assert get_place.status_code == 200
    assert get_place.json()["external_id"] == 111


def test_reject_duplicate_external_place(client):
    project_id = client.post("/projects", json={"name": "Project"}).json()["id"]
    first = client.post(f"/projects/{project_id}/places", json={"external_id": 111})
    assert first.status_code == 201

    duplicate = client.post(f"/projects/{project_id}/places", json={"external_id": 111})
    assert duplicate.status_code == 409


def test_max_10_places_rule(client):
    project_id = client.post("/projects", json={"name": "Project"}).json()["id"]
    for external_id in [111, 222, 333, 444, 555, 666, 777, 888, 999, 1000]:
        response = client.post(f"/projects/{project_id}/places", json={"external_id": external_id})
        assert response.status_code == 201

    overflow = client.post(f"/projects/{project_id}/places", json={"external_id": 1001})
    assert overflow.status_code == 400


def test_notes_and_visited_updates_and_completion(client):
    response = client.post(
        "/projects",
        json={"name": "Trip", "places": [{"external_id": 111}, {"external_id": 222}]},
    )
    project = response.json()
    project_id = project["id"]
    place_1 = project["places"][0]["id"]
    place_2 = project["places"][1]["id"]

    update_notes = client.patch(f"/projects/{project_id}/places/{place_1}", json={"notes": "Updated note"})
    assert update_notes.status_code == 200
    assert update_notes.json()["notes"] == "Updated note"

    visit_first = client.patch(f"/projects/{project_id}/places/{place_1}", json={"is_visited": True})
    assert visit_first.status_code == 200
    still_not_completed = client.get(f"/projects/{project_id}")
    assert still_not_completed.json()["is_completed"] is False

    visit_second = client.patch(f"/projects/{project_id}/places/{place_2}", json={"is_visited": True})
    assert visit_second.status_code == 200
    now_completed = client.get(f"/projects/{project_id}")
    assert now_completed.json()["is_completed"] is True


def test_delete_project_blocked_if_any_place_visited(client):
    project_id = client.post("/projects", json={"name": "Project"}).json()["id"]
    place = client.post(f"/projects/{project_id}/places", json={"external_id": 111}).json()

    visited = client.patch(f"/projects/{project_id}/places/{place['id']}", json={"is_visited": True})
    assert visited.status_code == 200

    delete_response = client.delete(f"/projects/{project_id}")
    assert delete_response.status_code == 409


def test_add_place_returns_502_when_artic_is_unavailable(client):
    class FailingClient:
        def place_exists(self, external_id: int):
            raise ArtInstituteServiceError("upstream down")

    app.dependency_overrides[get_artic_client] = lambda: FailingClient()
    try:
        project_id = client.post("/projects", json={"name": "Project"}).json()["id"]
        response = client.post(f"/projects/{project_id}/places", json={"external_id": 111})
        assert response.status_code == 502
    finally:
        app.dependency_overrides.pop(get_artic_client, None)


def test_list_places_supports_pagination_and_filters(client):
    project_id = client.post("/projects", json={"name": "Project"}).json()["id"]
    first = client.post(f"/projects/{project_id}/places", json={"external_id": 111}).json()
    second = client.post(f"/projects/{project_id}/places", json={"external_id": 222}).json()
    client.post(f"/projects/{project_id}/places", json={"external_id": 333})

    client.patch(f"/projects/{project_id}/places/{second['id']}", json={"is_visited": True})

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
