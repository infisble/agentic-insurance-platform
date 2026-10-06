import hashlib
import io
import uuid
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aip.core.claims.service import get_claim
from aip.core.documents.models import Document
from aip.core.errors import NotFound, ValidationFailed

ALLOWED_TYPES = {"application/pdf", "text/plain"}
MAX_SIZE = 20 * 1024 * 1024


def extract_text(data: bytes, content_type: str) -> tuple[str, int | None]:
    """Digital PDFs and plain text only. Scans need OCR (ADR 0007), which is not wired yet:
    a scan yields empty text and the pipeline escalates the claim to a human."""
    if content_type == "text/plain":
        return data.decode("utf-8"), None
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip(), len(pages)


async def add_document(
    session: AsyncSession,
    claim_id: uuid.UUID,
    filename: str,
    content_type: str,
    data: bytes,
    storage_dir: Path,
) -> Document:
    await get_claim(session, claim_id)
    if content_type not in ALLOWED_TYPES:
        raise ValidationFailed(f"Unsupported content type {content_type}")
    if len(data) > MAX_SIZE:
        raise ValidationFailed("File too large")

    digest = hashlib.sha256(data).hexdigest()
    existing = await session.scalar(
        select(Document).where(Document.claim_id == claim_id, Document.sha256 == digest)
    )
    if existing is not None:
        return existing

    try:
        text, pages = extract_text(data, content_type)
    except Exception as exc:  # malformed PDF
        raise ValidationFailed(f"Could not read document: {exc}") from exc

    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / f"{digest}{Path(filename).suffix.lower()}"
    path.write_bytes(data)

    doc = Document(
        claim_id=claim_id,
        filename=Path(filename).name,
        content_type=content_type,
        sha256=digest,
        size=len(data),
        storage_path=str(path),
        page_count=pages,
        text=text,
    )
    session.add(doc)
    await session.flush()
    return doc


async def list_documents(session: AsyncSession, claim_id: uuid.UUID) -> list[Document]:
    await get_claim(session, claim_id)
    result = await session.scalars(
        select(Document).where(Document.claim_id == claim_id).order_by(Document.created_at)
    )
    return list(result)


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFound(f"Document {document_id} not found")
    return doc
