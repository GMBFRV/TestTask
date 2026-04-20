from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_basic_auth
from app.dependencies import get_artic_client
from app.db import get_db
from app.models import ProjectPlace
from app.schemas import PaginatedPlacesResponse, PlaceCreate, PlaceRead, PlaceUpdate
from app.services.artic_client import ArtInstituteClient, ArtInstituteServiceError
from app.services.project_rules import (
    ensure_not_duplicate_external_id,
    ensure_place_limit,
    require_project,
    sync_project_completion,
)

router = APIRouter(prefix="/projects/{project_id}/places", tags=["places"])


@router.post("", response_model=PlaceRead, status_code=status.HTTP_201_CREATED)
def add_place_to_project(
    project_id: int,
    payload: PlaceCreate,
    _: None = Depends(require_basic_auth),
    db: Session = Depends(get_db),
    artic_client: ArtInstituteClient = Depends(get_artic_client),
) -> ProjectPlace:
    project = require_project(db, project_id)
    ensure_place_limit(db, project_id, places_to_add=1)
    ensure_not_duplicate_external_id(db, project_id, payload.external_id)

    try:
        # Surface third-party failures as 502 to indicate upstream dependency issues.
        exists, title = artic_client.place_exists(payload.external_id)
    except ArtInstituteServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Art Institute API is temporarily unavailable.",
        ) from exc
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"External place {payload.external_id} does not exist in Art Institute API.",
        )

    place = ProjectPlace(
        project_id=project_id,
        external_id=payload.external_id,
        title=title,
        notes=payload.notes,
        is_visited=False,
    )
    db.add(place)
    sync_project_completion(db, project)
    db.commit()
    db.refresh(place)
    return place


@router.get("", response_model=PaginatedPlacesResponse)
def list_project_places(
    project_id: int,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    is_visited: bool | None = Query(default=None),
    q: str | None = Query(default=None),
) -> PaginatedPlacesResponse:
    require_project(db, project_id)
    query = db.query(ProjectPlace).filter(ProjectPlace.project_id == project_id)
    if is_visited is not None:
        query = query.filter(ProjectPlace.is_visited == is_visited)
    if q:
        query = query.filter(ProjectPlace.title.ilike(f"%{q}%"))

    total = query.with_entities(func.count(ProjectPlace.id)).scalar() or 0
    items = query.order_by(ProjectPlace.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedPlacesResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{place_id}", response_model=PlaceRead)
def get_project_place(project_id: int, place_id: int, db: Session = Depends(get_db)) -> ProjectPlace:
    require_project(db, project_id)
    place = db.query(ProjectPlace).filter(ProjectPlace.project_id == project_id, ProjectPlace.id == place_id).first()
    if not place:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found in this project.")
    return place


@router.patch("/{place_id}", response_model=PlaceRead)
def update_project_place(
    project_id: int,
    place_id: int,
    payload: PlaceUpdate,
    _: None = Depends(require_basic_auth),
    db: Session = Depends(get_db),
) -> ProjectPlace:
    project = require_project(db, project_id)
    place = db.query(ProjectPlace).filter(ProjectPlace.project_id == project_id, ProjectPlace.id == place_id).first()
    if not place:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found in this project.")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(place, field, value)

    # Completion is derived from place visited states and must stay in sync.
    sync_project_completion(db, project)
    db.commit()
    db.refresh(place)
    return place
