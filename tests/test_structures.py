from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.modules.structures.schemas import StructureCreate, StructureType, StructureUpdate
from app.modules.structures.service import project_structures_query


def test_structure_type_is_explicit() -> None:
    payload = StructureCreate(name="Wall SM1", structure_type=StructureType.WALL)
    assert payload.structure_type == StructureType.WALL


def test_structure_update_rejects_explicit_null_name() -> None:
    with pytest.raises(ValidationError):
        StructureUpdate(name=None)


def test_project_structures_query_is_project_scoped() -> None:
    project_id = uuid4()
    query = str(
        project_structures_query(project_id).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(project_id) in query
    assert "structures.project_id" in query
