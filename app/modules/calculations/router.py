from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.calculations.schemas import (
    CalculationCreate,
    CalculationResponse,
    CalculationStatusUpdate,
)
from app.modules.calculations.service import (
    calculate,
    project_calculations_query,
    validate_structure,
)
from app.modules.domain.models import AuditEvent, Calculation
from app.modules.projects.access import ProjectPermission, require_project_permission

router = APIRouter(prefix="/projects/{project_id}/calculations", tags=["calculations"])


@router.post("", response_model=CalculationResponse, status_code=status.HTTP_201_CREATED)
async def create_calculation(
    project_id: UUID,
    payload: CalculationCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Calculation:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_CALCULATIONS
    )
    await validate_structure(session, project_id, payload.structure_id)
    formula_version, input_data, result = calculate(payload.calculation_type, payload.input_data)
    calculation = Calculation(
        project_id=project_id,
        structure_id=payload.structure_id,
        title=payload.title,
        calculation_type=payload.calculation_type.value,
        status="draft",
        formula_version=formula_version,
        input_data=input_data,
        result=result,
        sources=[source.model_dump(mode="json") for source in payload.sources],
        notes=payload.notes,
        created_by_id=current_user.id,
    )
    session.add(calculation)
    await session.flush()
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=current_user.id,
            entity_type="calculation",
            entity_id=calculation.id,
            action="created",
            new_value={
                "title": calculation.title,
                "calculation_type": calculation.calculation_type,
                "status": calculation.status,
                "formula_version": calculation.formula_version,
            },
        )
    )
    await session.commit()
    await session.refresh(calculation)
    return calculation


@router.get("", response_model=list[CalculationResponse])
async def list_calculations(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> list[Calculation]:
    await require_project_permission(session, current_user, project_id)
    return list((await session.scalars(project_calculations_query(project_id))).all())


@router.patch("/{calculation_id}/status", response_model=CalculationResponse)
async def update_calculation_status(
    project_id: UUID,
    calculation_id: UUID,
    payload: CalculationStatusUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Calculation:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_CALCULATIONS
    )
    calculation = (
        await session.scalars(
            select(Calculation).where(
                Calculation.id == calculation_id,
                Calculation.project_id == project_id,
            )
        )
    ).one_or_none()
    if calculation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calculation not found")
    old_status = calculation.status
    allowed_transition = {"draft": "checked", "checked": "approved"}.get(old_status)
    if payload.status.value != allowed_transition:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Calculation status must progress from draft to checked to approved",
        )
    calculation.status = payload.status.value
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=current_user.id,
            entity_type="calculation",
            entity_id=calculation.id,
            action="status_changed",
            old_value={"status": old_status},
            new_value={"status": calculation.status},
        )
    )
    await session.commit()
    await session.refresh(calculation)
    return calculation
