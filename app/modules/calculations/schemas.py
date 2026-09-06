from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CalculationType(StrEnum):
    CONCRETE_POUR = "concrete_pour"
    WALL_REBAR = "wall_rebar"
    PROJECT_REBAR_SCHEDULE = "project_rebar_schedule"


class CalculationStatus(StrEnum):
    DRAFT = "draft"
    CHECKED = "checked"
    APPROVED = "approved"


class FiniteModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class SourceReference(FiniteModel):
    document_id: UUID | None = None
    document_name: str | None = Field(default=None, max_length=255)
    page: int | None = Field(default=None, ge=1, le=1000000000)
    drawing: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=500)


class ConcretePourInput(FiniteModel):
    length_m: float = Field(gt=0, le=10000)
    height_m: float = Field(gt=0, le=1000)
    thickness_m: float = Field(gt=0, le=20)
    openings_m3: float = Field(default=0, ge=0, le=1e12)
    embedded_items_m3: float = Field(default=0, ge=0, le=1e12)
    rebar_mass_kg: float = Field(default=0, ge=0, le=1e12)
    subtract_rebar_displacement: bool = False
    reserve_percent: float = Field(default=3, ge=0, le=25)
    concrete_class: str = Field(default="C25/30", min_length=1, max_length=32)
    pour_mark: str | None = Field(default=None, max_length=128)
    specified_gross_volume_m3: float | None = Field(default=None, gt=0, le=1e12)
    specified_quantity: int | None = Field(default=None, ge=1, le=10000)
    specified_unit_volume_m3: float | None = Field(default=None, gt=0, le=1e12)
    project_element_mark: str | None = Field(default=None, max_length=64)


class WallRebarInput(FiniteModel):
    wall_length_m: float = Field(gt=0, le=10000)
    wall_height_m: float = Field(gt=0, le=1000)
    vertical_diameter_mm: float = Field(gt=0, le=80)
    vertical_spacing_mm: float = Field(ge=1, le=2000)
    vertical_layers: int = Field(default=2, ge=1, le=6)
    vertical_lap_m: float = Field(default=0, ge=0, le=20)
    horizontal_diameter_mm: float = Field(gt=0, le=80)
    horizontal_spacing_mm: float = Field(ge=1, le=2000)
    horizontal_layers: int = Field(default=2, ge=1, le=6)
    horizontal_lap_m: float = Field(default=0, ge=0, le=20)
    extra_details_mass_kg: float = Field(default=0, ge=0, le=1e12)
    waste_percent: float = Field(default=3, ge=0, le=25)
    steel_grade: str = Field(default="A500C", min_length=1, max_length=32)
    tie_wire_percent: float = Field(default=1.2, ge=0, le=10)
    node_description: str | None = Field(default=None, max_length=2000)


class ProjectRebarItem(FiniteModel):
    mark: str = Field(min_length=1, max_length=32)
    steel: str = Field(min_length=1, max_length=64)
    diameter_mm: float | None = Field(default=None, gt=0, le=100)
    bar_length_mm: float | None = Field(default=None, gt=0, le=1e12)
    total_length_m: float | None = Field(default=None, gt=0, le=1e12)
    quantity: int | None = Field(default=None, ge=1, le=1000000000)
    mass_kg: float = Field(gt=0, le=1e12)
    dimensions: str | None = Field(default=None, max_length=500)
    placement: str | None = Field(default=None, max_length=1000)


class ProjectRebarScheduleInput(FiniteModel):
    element_mark: str = Field(min_length=1, max_length=64)
    element_name: str = Field(min_length=1, max_length=255)
    concrete_cover_mm: float = Field(default=35, ge=0, le=300)
    tie_wire_diameter_mm: float = Field(default=1.2, gt=0, le=10)
    items: list[ProjectRebarItem] = Field(min_length=1, max_length=500)
    declared_total_mass_kg: float = Field(gt=0, le=1e12)
    installation_notes: list[str] = Field(default_factory=list, max_length=100)


class CalculationCreate(FiniteModel):
    title: str = Field(min_length=1, max_length=255)
    structure_id: UUID | None = None
    calculation_type: CalculationType
    input_data: dict[str, Any]
    sources: list[SourceReference] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=4000)


class CalculationStatusUpdate(FiniteModel):
    status: CalculationStatus


class CalculationResponse(FiniteModel):
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
