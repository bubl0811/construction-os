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
from app.modules.domain.models import AuditEvent, Calculation, Document, DocumentPage, SheetRevision
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
    source_snapshots = []
    for source in payload.sources:
        snapshot = source.model_dump(mode="json")
        if source.document_id is None:
            snapshot["source_type"] = "USER_INPUT"
            source_snapshots.append(snapshot)
            continue
        document = await session.scalar(
            select(Document).where(
                Document.id == source.document_id, Document.project_id == project_id
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Source document not found")
        if source.page is not None:
            page = await session.scalar(
                select(DocumentPage.id).where(
                    DocumentPage.document_id == source.document_id,
                    DocumentPage.project_id == project_id,
                    DocumentPage.page_number == source.page,
                )
            )
            if page is None:
                raise HTTPException(status_code=422, detail="Source page not found")
            sheet = await session.scalar(
                select(SheetRevision).where(
                    SheetRevision.project_id == project_id,
                    SheetRevision.document_id == document.id,
                    SheetRevision.page_number == source.page,
                )
            )
            if sheet is not None:
                if sheet.status == "archived":
                    raise HTTPException(
                        status_code=409, detail="Source drawing revision is archived"
                    )
                snapshot.update(
                    {
                        "sheet_revision_id": str(sheet.id),
                        "revision": sheet.revision,
                        "drawing_code": sheet.drawing_code,
                        "revision_status": sheet.status,
                    }
                )
        snapshot.update(
            {
                "document_name": document.name,
                "sha256": document.sha256,
                "source_type": "DOCUMENT",
                "document_created_at": document.created_at.isoformat(),
            }
        )
        source_snapshots.append(snapshot)
    formula_version, input_data, result = calculate(payload.calculation_type, payload.input_data)
    input_data["value_sources"] = {key: {"type": "USER_INPUT"} for key in input_data}
    document_sources = [
        source for source in source_snapshots if source.get("source_type") == "DOCUMENT"
    ]
    if document_sources:
        for key in {
            "specified_gross_volume_m3",
            "specified_unit_volume_m3",
            "specified_quantity",
            "project_element_mark",
        }:
            if input_data.get(key) is not None:
                input_data["value_sources"][key] = {
                    "type": "DOCUMENT",
                    "references": document_sources,
                }
    calculation = Calculation(
        project_id=project_id,
        structure_id=payload.structure_id,
        title=payload.title,
        calculation_type=payload.calculation_type.value,
        status="draft",
        formula_version=formula_version,
        input_data=input_data,
        result=result,
        sources=source_snapshots,
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
            select(Calculation)
            .where(
                Calculation.id == calculation_id,
                Calculation.project_id == project_id,
            )
            .with_for_update()
        )
    ).one_or_none()
    if calculation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calculation not found")
    if calculation.result.get("requires_review"):
        raise HTTPException(status_code=409, detail="Specification totals require reconciliation")
    for source in calculation.sources:
        if source.get("document_id") is None:
            continue
        document = await session.scalar(
            select(Document).where(
                Document.project_id == project_id, Document.id == UUID(source["document_id"])
            )
        )
        if document is None or not source.get("sha256") or document.sha256 != source["sha256"]:
            raise HTTPException(status_code=409, detail="Source document must be rechecked")
        if source.get("sheet_revision_id"):
            sheet = await session.scalar(
                select(SheetRevision).where(
                    SheetRevision.project_id == project_id,
                    SheetRevision.id == UUID(source["sheet_revision_id"]),
                )
            )
            if sheet is None or sheet.status != "current":
                raise HTTPException(status_code=409, detail="Source drawing is not current")
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
