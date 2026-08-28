import math
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculations.schemas import (
    CalculationType,
    ConcretePourInput,
    WallRebarInput,
)
from app.modules.domain.models import Calculation, Structure

FORMULA_VERSIONS = {
    CalculationType.CONCRETE_POUR: "concrete-wall-v1",
    CalculationType.WALL_REBAR: "wall-rebar-v1",
}
STEEL_DENSITY_KG_M3 = 7850.0


def _round(value: float, digits: int = 3) -> float:
    return round(value + 0.0, digits)


def calculate_concrete_pour(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        data = ConcretePourInput.model_validate(raw)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.errors()
        ) from error
    gross_m3 = data.length_m * data.height_m * data.thickness_m
    rebar_displacement_m3 = (
        data.rebar_mass_kg / STEEL_DENSITY_KG_M3 if data.subtract_rebar_displacement else 0
    )
    deductions_m3 = data.openings_m3 + data.embedded_items_m3 + rebar_displacement_m3
    if deductions_m3 >= gross_m3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Deductions must be smaller than gross concrete volume",
        )
    net_m3 = gross_m3 - deductions_m3
    order_m3 = net_m3 * (1 + data.reserve_percent / 100)
    normalized = data.model_dump(mode="json")
    result = {
        "gross_volume_m3": _round(gross_m3),
        "openings_m3": _round(data.openings_m3),
        "embedded_items_m3": _round(data.embedded_items_m3),
        "rebar_displacement_m3": _round(rebar_displacement_m3),
        "net_volume_m3": _round(net_m3),
        "reserve_volume_m3": _round(order_m3 - net_m3),
        "order_volume_m3": _round(order_m3),
        "concrete_class": data.concrete_class,
        "formula": (
            "Vзамовлення = (L × H × t − Vпрорізів − Vзакладних − Vарматури) "
            "× (1 + запас/100)"
        ),
    }
    return normalized, result


def _bar_unit_mass(diameter_mm: float) -> float:
    return diameter_mm * diameter_mm / 162.0


def calculate_wall_rebar(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        data = WallRebarInput.model_validate(raw)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.errors()
        ) from error

    vertical_count_per_layer = math.ceil(data.wall_length_m * 1000 / data.vertical_spacing_mm) + 1
    vertical_count = vertical_count_per_layer * data.vertical_layers
    vertical_bar_length = data.wall_height_m + data.vertical_lap_m
    vertical_total_m = vertical_count * vertical_bar_length
    vertical_mass_kg = vertical_total_m * _bar_unit_mass(data.vertical_diameter_mm)

    horizontal_count_per_layer = (
        math.ceil(data.wall_height_m * 1000 / data.horizontal_spacing_mm) + 1
    )
    horizontal_count = horizontal_count_per_layer * data.horizontal_layers
    horizontal_bar_length = data.wall_length_m + data.horizontal_lap_m
    horizontal_total_m = horizontal_count * horizontal_bar_length
    horizontal_mass_kg = horizontal_total_m * _bar_unit_mass(data.horizontal_diameter_mm)

    base_mass_kg = vertical_mass_kg + horizontal_mass_kg + data.extra_details_mass_kg
    total_mass_kg = base_mass_kg * (1 + data.waste_percent / 100)
    tie_wire_kg = total_mass_kg * data.tie_wire_percent / 100
    intersections = vertical_count_per_layer * horizontal_count_per_layer * min(
        data.vertical_layers, data.horizontal_layers
    )
    normalized = data.model_dump(mode="json")
    result = {
        "vertical": {
            "count": vertical_count,
            "count_per_layer": vertical_count_per_layer,
            "bar_length_m": _round(vertical_bar_length),
            "total_length_m": _round(vertical_total_m),
            "unit_mass_kg_m": _round(_bar_unit_mass(data.vertical_diameter_mm), 4),
            "mass_kg": _round(vertical_mass_kg, 1),
        },
        "horizontal": {
            "count": horizontal_count,
            "count_per_layer": horizontal_count_per_layer,
            "bar_length_m": _round(horizontal_bar_length),
            "total_length_m": _round(horizontal_total_m),
            "unit_mass_kg_m": _round(_bar_unit_mass(data.horizontal_diameter_mm), 4),
            "mass_kg": _round(horizontal_mass_kg, 1),
        },
        "extra_details_mass_kg": _round(data.extra_details_mass_kg, 1),
        "base_mass_kg": _round(base_mass_kg, 1),
        "waste_mass_kg": _round(total_mass_kg - base_mass_kg, 1),
        "total_mass_kg": _round(total_mass_kg, 1),
        "tie_wire_kg": _round(tie_wire_kg, 1),
        "estimated_intersections": intersections,
        "steel_grade": data.steel_grade,
        "formula": "m = Σ(n × l × d²/162) + маса деталей; підсумок із технологічним запасом",
    }
    return normalized, result


def calculate(
    calculation_type: CalculationType, raw: dict[str, Any]
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if calculation_type == CalculationType.CONCRETE_POUR:
        input_data, result = calculate_concrete_pour(raw)
    else:
        input_data, result = calculate_wall_rebar(raw)
    return FORMULA_VERSIONS[calculation_type], input_data, result


def project_calculations_query(project_id: UUID) -> Select[tuple[Calculation]]:
    return (
        select(Calculation)
        .where(Calculation.project_id == project_id)
        .order_by(Calculation.created_at.desc(), Calculation.id.desc())
    )


async def validate_structure(
    session: AsyncSession, project_id: UUID, structure_id: UUID | None
) -> None:
    if structure_id is None:
        return
    exists = await session.scalar(
        select(Structure.id).where(
            Structure.id == structure_id,
            Structure.project_id == project_id,
        )
    )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure not found")
