import csv
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.domain.models import Calculation
from app.modules.projects.access import require_project_permission

router = APIRouter(prefix="/projects/{project_id}/reports", tags=["project reports"])


def csv_cell(value: object) -> str:
    text = str(value)
    # Spreadsheet applications must not execute project/user labels as formulas.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@router.get("/calculations.csv")
async def calculations_report(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> Response:
    await require_project_permission(session, current_user, project_id)
    calculations = await session.scalars(
        select(Calculation)
        .where(Calculation.project_id == project_id)
        .order_by(Calculation.created_at, Calculation.id)
    )
    stream = StringIO()
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(
        ["Проєкт", "Назва", "Тип", "Статус", "Формула", "Результат", "Джерела", "Дата", "Автор"]
    )
    import json

    for item in calculations:
        writer.writerow(
            [
                csv_cell(value)
                for value in [
                    item.project_id,
                    item.title,
                    item.calculation_type,
                    item.status,
                    item.formula_version,
                    json.dumps(item.result, ensure_ascii=False),
                    json.dumps(item.sources, ensure_ascii=False),
                    item.created_at.isoformat(),
                    item.created_by_id,
                ]
            ]
        )
    return Response(
        "\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="project-calculations.csv"'},
    )
