from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ProjectPlace, TravelProject


MAX_PLACES_PER_PROJECT = 10


def require_project(db: Session, project_id: int) -> TravelProject:
    project = db.get(TravelProject, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def ensure_place_limit(db: Session, project_id: int, places_to_add: int = 1) -> None:
    places_count = db.scalar(select(func.count(ProjectPlace.id)).where(ProjectPlace.project_id == project_id)) or 0
    if places_count + places_to_add > MAX_PLACES_PER_PROJECT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A project can contain at most {MAX_PLACES_PER_PROJECT} places.",
        )


def ensure_not_duplicate_external_id(db: Session, project_id: int, external_id: int) -> None:
    exists = db.scalar(
        select(ProjectPlace.id).where(
            ProjectPlace.project_id == project_id,
            ProjectPlace.external_id == external_id,
        )
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This external place is already added to the project.",
        )


def sync_project_completion(db: Session, project: TravelProject) -> None:
    db.flush()
    total_places = db.scalar(select(func.count(ProjectPlace.id)).where(ProjectPlace.project_id == project.id)) or 0
    visited_places = db.scalar(
        select(func.count(ProjectPlace.id)).where(ProjectPlace.project_id == project.id, ProjectPlace.is_visited.is_(True))
    ) or 0
    project.is_completed = total_places > 0 and total_places == visited_places
