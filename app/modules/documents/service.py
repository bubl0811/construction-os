import hashlib
import os
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.domain.models import Document, DocumentPage


class DocumentValidationError(ValueError):
    pass


def safe_document_name(filename: str | None) -> str:
    basename = Path(filename or "document.pdf").name.strip()
    cleaned = "".join(character for character in basename if character.isprintable())
    return cleaned[:255] or "document.pdf"


def document_storage_file(storage_root: Path, storage_key: str) -> Path:
    root = storage_root.resolve()
    candidate = (root / storage_key).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Invalid document storage key")
    return candidate


def persist_pdf(
    source: BinaryIO,
    temporary_path: Path,
    final_path: Path,
    max_size_bytes: int,
) -> tuple[str, int]:
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    source.seek(0)
    digest = hashlib.sha256()
    size = 0
    header = b""

    try:
        with temporary_path.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                if not header:
                    header = chunk[:5]
                size += len(chunk)
                if size > max_size_bytes:
                    raise DocumentValidationError(
                        f"PDF exceeds the {max_size_bytes // (1024 * 1024)} MB limit"
                    )
                digest.update(chunk)
                target.write(chunk)

        if size == 0 or header != b"%PDF-":
            raise DocumentValidationError("Uploaded file is not a valid PDF")

        try:
            reader = PdfReader(temporary_path)
            if reader.is_encrypted:
                raise DocumentValidationError("Password-protected PDFs are not supported")
            page_count = len(reader.pages)
        except PdfReadError as error:
            raise DocumentValidationError("Uploaded PDF is damaged or unreadable") from error

        if page_count < 1:
            raise DocumentValidationError("PDF does not contain any pages")

        os.replace(temporary_path, final_path)
        return digest.hexdigest(), page_count
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def project_documents_query(project_id: UUID) -> Select[tuple[Document, int]]:
    return (
        select(Document, func.count(DocumentPage.id).label("page_count"))
        .outerjoin(DocumentPage, DocumentPage.document_id == Document.id)
        .where(Document.project_id == project_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )


async def get_project_document(
    session: AsyncSession, project_id: UUID, document_id: UUID
) -> Document | None:
    return cast(
        Document | None,
        await session.scalar(
            select(Document).where(Document.project_id == project_id, Document.id == document_id)
        ),
    )
