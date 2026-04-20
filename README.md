# Travel Projects API (FastAPI + SQLite)

Backend for managing travel projects and places validated via the Art Institute of Chicago API.

## Stack

- FastAPI
- SQLAlchemy
- SQLite
- Pytest

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

API docs: `http://127.0.0.1:8000/docs`

## Run Tests

```bash
.\.venv\Scripts\python -m pytest -q
```

## Implemented Rules

- Creating an empty project (without places) is allowed; places can be added later.
- Create/list/get/update/delete travel projects.
- Create project with optional places in a single request.
- Add/list/get/update places inside a project.
- Validate external place IDs against Art Institute API before storing.
- Return `502 Bad Gateway` when the Art Institute API is unavailable.
- Prevent duplicate external place in the same project.
- Enforce max 10 places per project.
- Mark place as visited and auto-mark project completed when all places are visited.
- Block project deletion if any place in that project is marked visited.

## Listing Pagination & Filtering

Both listing endpoints return metadata:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 10
}
```

### GET /projects

Query params:
- `page` (default `1`, min `1`)
- `page_size` (default `10`, range `1..100`)
- `is_completed` (`true` / `false`)
- `start_date_from` (ISO date)
- `start_date_to` (ISO date)
- `q` (case-insensitive project name search)

Example:
```text
GET /projects?page=1&page_size=5&is_completed=true&q=trip&start_date_from=2026-01-01&start_date_to=2026-12-31
```

### GET /projects/{project_id}/places

Query params:
- `page` (default `1`, min `1`)
- `page_size` (default `10`, range `1..100`)
- `is_visited` (`true` / `false`)
- `q` (case-insensitive place title search)

Example:
```text
GET /projects/1/places?page=1&page_size=5&is_visited=false&q=artwork
```
