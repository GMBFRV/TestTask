from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_artic_client
from app.db import get_db
from app.models import ProjectPlace, TravelProject
from app.schemas import ProjectCreate, ProjectRead, ProjectUpdate, ProjectWithPlacesRead
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


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[TravelProject]:
    return db.query(TravelProject).order_by(TravelProject.id.asc()).all()


@router.get("/{project_id}", response_model=ProjectWithPlacesRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> TravelProject:
    project = (
        db.query(TravelProject).options(selectinload(TravelProject.places)).filter(TravelProject.id == project_id).first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> TravelProject:
    project = require_project(db, project_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
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
