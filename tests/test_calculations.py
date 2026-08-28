from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.modules.calculations.schemas import CalculationType
from app.modules.calculations.service import (
    calculate_concrete_pour,
    calculate_wall_rebar,
    project_calculations_query,
)


def test_concrete_pour_accounts_for_deductions_rebar_and_reserve() -> None:
    _, result = calculate_concrete_pour(
        {
            "length_m": 29,
            "height_m": 3.1,
            "thickness_m": 0.5,
            "openings_m3": 1.2,
            "embedded_items_m3": 0.1,
            "rebar_mass_kg": 7850,
            "subtract_rebar_displacement": True,
            "reserve_percent": 3,
            "concrete_class": "C30/37",
        }
    )
    assert result["gross_volume_m3"] == 44.95
    assert result["rebar_displacement_m3"] == 1.0
    assert result["net_volume_m3"] == 42.65
    assert result["order_volume_m3"] == 43.93


def test_concrete_pour_rejects_deductions_larger_than_volume() -> None:
    with pytest.raises(HTTPException):
        calculate_concrete_pour(
            {"length_m": 1, "height_m": 1, "thickness_m": 0.2, "openings_m3": 1}
        )


def test_wall_rebar_calculates_both_directions_and_layers() -> None:
    _, result = calculate_wall_rebar(
        {
            "wall_length_m": 10,
            "wall_height_m": 3,
            "vertical_diameter_mm": 16,
            "vertical_spacing_mm": 200,
            "vertical_layers": 2,
            "vertical_lap_m": 0.8,
            "horizontal_diameter_mm": 12,
            "horizontal_spacing_mm": 200,
            "horizontal_layers": 2,
            "horizontal_lap_m": 0.6,
            "extra_details_mass_kg": 25,
            "waste_percent": 3,
        }
    )
    assert result["vertical"]["count"] == 102
    assert result["horizontal"]["count"] == 32
    assert result["total_mass_kg"] > result["base_mass_kg"] > 0
    assert result["tie_wire_kg"] > 0


def test_project_calculations_query_is_project_scoped() -> None:
    project_id = uuid4()
    query = str(
        project_calculations_query(project_id).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(project_id) in query
    assert "calculations.project_id" in query
    assert CalculationType.CONCRETE_POUR.value == "concrete_pour"
