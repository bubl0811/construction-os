from io import BytesIO
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from pypdf import PdfWriter
from sqlalchemy.dialects import postgresql

from app.core.security import (
    create_document_upload_token,
    decode_document_upload_token,
)
from app.main import app
from app.modules.documents.service import (
    DocumentValidationError,
    document_storage_file,
    persist_pdf,
    project_documents_query,
    safe_document_name,
)


def pdf_bytes(page_count: int = 2) -> BytesIO:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output


def test_persist_pdf_hashes_and_counts_pages(tmp_path: Path) -> None:
    temporary_path = tmp_path / "document.upload"
    final_path = tmp_path / "document.pdf"

    digest, page_count = persist_pdf(
        pdf_bytes(), temporary_path, final_path, max_size_bytes=1024 * 1024
    )

    assert len(digest) == 64
    assert page_count == 2
    assert final_path.read_bytes().startswith(b"%PDF-")
    assert not temporary_path.exists()


def test_persist_pdf_rejects_non_pdf(tmp_path: Path) -> None:
    temporary_path = tmp_path / "document.upload"
    final_path = tmp_path / "document.pdf"

    with pytest.raises(DocumentValidationError, match="valid PDF"):
        persist_pdf(BytesIO(b"not a pdf"), temporary_path, final_path, max_size_bytes=1024)

    assert not temporary_path.exists()
    assert not final_path.exists()


def test_document_name_drops_path_components() -> None:
    assert safe_document_name("../../drawings/wall-sm1.pdf") == "wall-sm1.pdf"


def test_document_storage_file_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="storage key"):
        document_storage_file(tmp_path, "../outside.pdf")


def test_project_documents_query_is_project_scoped() -> None:
    project_id = uuid4()
    query = str(
        project_documents_query(project_id).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(project_id) in query
    assert "documents.project_id" in query


def test_document_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    collection_path = "/api/v1/projects/{project_id}/documents"
    download_path = "/api/v1/projects/{project_id}/documents/{document_id}/download"

    assert {"get", "post"} <= set(paths[collection_path])
    assert "get" in paths[download_path]
    assert "post" in paths[f"{collection_path}/upload-session"]
    assert "post" in paths[f"{collection_path}/direct-upload"]


def test_document_upload_token_is_project_scoped() -> None:
    user_id = uuid4()
    project_id = uuid4()
    token = create_document_upload_token(user_id, project_id)

    assert decode_document_upload_token(token, project_id) == user_id
    with pytest.raises(jwt.InvalidTokenError):
        decode_document_upload_token(token, uuid4())
