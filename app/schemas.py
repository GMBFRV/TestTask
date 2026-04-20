from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class PlaceImport(BaseModel):
    external_id: int = Field(..., gt=0)


class PlaceCreate(PlaceImport):
    notes: str | None = None


class PlaceUpdate(BaseModel):
    notes: str | None = None
    is_visited: bool | None = None

    @model_validator(mode="after")
    def validate_not_empty(self) -> "PlaceUpdate":
        if self.notes is None and self.is_visited is None:
            raise ValueError("At least one field (notes or is_visited) must be provided.")
        return self


class PlaceRead(BaseModel):
    id: int
    project_id: int
    external_id: int
    title: str | None
    notes: str | None
    is_visited: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    start_date: date | None = None
    places: list[PlaceCreate] = Field(default_factory=list, max_length=10)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    start_date: date | None = None

    @model_validator(mode="after")
    def validate_not_empty(self) -> "ProjectUpdate":
        if self.name is None and self.description is None and self.start_date is None:
            raise ValueError("At least one field (name, description, start_date) must be provided.")
        return self


class ProjectRead(BaseModel):
    id: int
    name: str
    description: str | None
    start_date: date | None
    is_completed: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectWithPlacesRead(ProjectRead):
    places: list[PlaceRead] = Field(default_factory=list)
