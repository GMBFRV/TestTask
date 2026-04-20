from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.auth import require_basic_auth
from app.dependencies import get_artic_client
from app.db import get_db
from app.models import ProjectPlace, TravelProject
from app.schemas import PaginatedProjectsResponse, ProjectCreate, ProjectRead, ProjectUpdate, ProjectWithPlacesRead
from app.services.artic_client import ArtInstituteClient, ArtInstituteServiceError
from app.services.project_rules import (
    ensure_not_duplicate_external_id,
    ensure_place_limit,
    require_project,
    sync_project_completion,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectWithPlacesRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    _: None = Depends(require_basic_auth),
    db: Session = Depends(get_db),
    artic_client: ArtInstituteClient = Depends(get_artic_client),
) -> TravelProject:
    external_ids = [place.external_id for place in payload.places]
    if len(external_ids) != len(set(external_ids)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate external IDs in request.")

    project = TravelProject(name=payload.name, description=payload.description, start_date=payload.start_date)
    db.add(project)
    db.flush()

    ensure_place_limit(db, project.id, places_to_add=len(payload.places))

    for place_payload in payload.places:
        ensure_not_duplicate_external_id(db, project.id, place_payload.external_id)
        try:
            # Upstream outages should be reported as 502 instead of a generic 500.
            exists, title = artic_client.place_exists(place_payload.external_id)
        except ArtInstituteServiceError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Art Institute API is temporarily unavailable.",
            ) from exc
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"External place {place_payload.external_id} does not exist in Art Institute API.",
            )
        db.add(
            ProjectPlace(
                project_id=project.id,
                external_id=place_payload.external_id,
                title=title,
                notes=place_payload.notes,
                is_visited=False,
            )
        )

    sync_project_completion(db, project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=PaginatedProjectsResponse)
def list_projects(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    is_completed: bool | None = Query(default=None),
    start_date_from: date | None = Query(default=None),
    start_date_to: date | None = Query(default=None),
    q: str | None = Query(default=None),
) -> PaginatedProjectsResponse:
    if start_date_from and start_date_to and start_date_from > start_date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date_from must be less than or equal to start_date_to.",
        )

    query = db.query(TravelProject)
    if is_completed is not None:
        query = query.filter(TravelProject.is_completed == is_completed)
    if start_date_from is not None:
        query = query.filter(TravelProject.start_date >= start_date_from)
    if start_date_to is not None:
        query = query.filter(TravelProject.start_date <= start_date_to)
    if q:
        query = query.filter(TravelProject.name.ilike(f"%{q}%"))

    total = query.with_entities(func.count(TravelProject.id)).scalar() or 0
    items = query.order_by(TravelProject.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedProjectsResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{project_id}", response_model=ProjectWithPlacesRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> TravelProject:
    project = (
        db.query(TravelProject).options(selectinload(TravelProject.places)).filter(TravelProject.id == project_id).first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    _: None = Depends(require_basic_auth),
    db: Session = Depends(get_db),
) -> TravelProject:
    project = require_project(db, project_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    _: None = Depends(require_basic_auth),
    db: Session = Depends(get_db),
) -> None:
    project = require_project(db, project_id)
    # Business rule: if any place was visited, deleting the project is not allowed.
    visited_exists = (
        db.query(ProjectPlace.id)
        .filter(ProjectPlace.project_id == project_id, ProjectPlace.is_visited.is_(True))
        .first()
    )
    if visited_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project cannot be deleted because it has visited places.",
        )

    db.delete(project)
    db.commit()
