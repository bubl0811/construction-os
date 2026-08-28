from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CalculationType(StrEnum):
    CONCRETE_POUR = "concrete_pour"
    WALL_REBAR = "wall_rebar"


class CalculationStatus(StrEnum):
    DRAFT = "draft"
    CHECKED = "checked"
    APPROVED = "approved"


class SourceReference(BaseModel):
    document_id: UUID | None = None
    document_name: str | None = Field(default=None, max_length=255)
    page: int | None = Field(default=None, ge=1)
    drawing: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=500)


class ConcretePourInput(BaseModel):
    length_m: float = Field(gt=0, le=10000)
    height_m: float = Field(gt=0, le=1000)
    thickness_m: float = Field(gt=0, le=20)
    openings_m3: float = Field(default=0, ge=0)
    embedded_items_m3: float = Field(default=0, ge=0)
    rebar_mass_kg: float = Field(default=0, ge=0)
    subtract_rebar_displacement: bool = False
    reserve_percent: float = Field(default=3, ge=0, le=25)
    concrete_class: str = Field(default="C25/30", min_length=1, max_length=32)
    pour_mark: str | None = Field(default=None, max_length=128)


class WallRebarInput(BaseModel):
    wall_length_m: float = Field(gt=0, le=10000)
    wall_height_m: float = Field(gt=0, le=1000)
    vertical_diameter_mm: float = Field(gt=0, le=80)
    vertical_spacing_mm: float = Field(gt=0, le=2000)
    vertical_layers: int = Field(default=2, ge=1, le=6)
    vertical_lap_m: float = Field(default=0, ge=0, le=20)
    horizontal_diameter_mm: float = Field(gt=0, le=80)
    horizontal_spacing_mm: float = Field(gt=0, le=2000)
    horizontal_layers: int = Field(default=2, ge=1, le=6)
    horizontal_lap_m: float = Field(default=0, ge=0, le=20)
    extra_details_mass_kg: float = Field(default=0, ge=0)
    waste_percent: float = Field(default=3, ge=0, le=25)
    steel_grade: str = Field(default="A500C", min_length=1, max_length=32)
    tie_wire_percent: float = Field(default=1.2, ge=0, le=10)
    node_description: str | None = Field(default=None, max_length=2000)


class CalculationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    structure_id: UUID | None = None
    calculation_type: CalculationType
    input_data: dict[str, Any]
    sources: list[SourceReference] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=4000)


class CalculationStatusUpdate(BaseModel):
    status: CalculationStatus


class CalculationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    structure_id: UUID | None
    title: str
    calculation_type: CalculationType
    status: CalculationStatus
    formula_version: str
    input_data: dict[str, Any]
    result: dict[str, Any]
    sources: list[dict[str, Any]]
    notes: str | None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
