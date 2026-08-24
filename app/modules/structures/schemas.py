from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StructureType(StrEnum):
    SITE = "site"
    BUILDING = "building"
    SECTION = "section"
    FLOOR = "floor"
    FOUNDATION = "foundation"
    WALL = "wall"
    SLAB = "slab"
    COLUMN = "column"
    BEAM = "beam"
    STAIR = "stair"
    OTHER = "other"


class StructureCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    structure_type: StructureType
    parent_id: UUID | None = None


class StructureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    structure_type: StructureType | None = None
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "StructureUpdate":
        for field_name in ("name", "structure_type"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class StructureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    parent_id: UUID | None
    name: str
    structure_type: StructureType
    created_at: datetime
    updated_at: datetime
