from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_artic_client
from app.db import get_db
from app.models import ProjectPlace
from app.schemas import PlaceCreate, PlaceRead, PlaceUpdate
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


@router.get("", response_model=list[PlaceRead])
def list_project_places(project_id: int, db: Session = Depends(get_db)) -> list[ProjectPlace]:
    require_project(db, project_id)
    return db.query(ProjectPlace).filter(ProjectPlace.project_id == project_id).order_by(ProjectPlace.id.asc()).all()


@router.get("/{place_id}", response_model=PlaceRead)
def get_project_place(project_id: int, place_id: int, db: Session = Depends(get_db)) -> ProjectPlace:
    require_project(db, project_id)
    place = db.query(ProjectPlace).filter(ProjectPlace.project_id == project_id, ProjectPlace.id == place_id).first()
    if not place:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found in this project.")
    return place


@router.patch("/{place_id}", response_model=PlaceRead)
def update_project_place(project_id: int, place_id: int, payload: PlaceUpdate, db: Session = Depends(get_db)) -> ProjectPlace:
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
