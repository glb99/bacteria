import uuid
from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path

from app.documents.document import DocumentRepository
from app.documents.entity_extractor import ENTITY_PROMPT, SendsForDetections
from app.documents.page_image import render_page_image
from app.documents.paginator import Paginate
from app.llm.embeddings import Embed
from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.core.file_system import FileSystem
from app.models import Document


def validate_document(
    file_name: str,
    document_repository: DocumentRepository,
) -> Document:
    """Reject a missing or duplicate file name and store a pending document."""
    if not file_name:
        raise HTTPException(status_code=400, detail="A file name is required.")
    if document_repository.get_by_file_name(file_name=file_name):
        raise HTTPException(
            status_code=400,
            detail=f"Document with file name '{file_name}' already exists.",
        )
    return document_repository.create_document(
        Document(file_name=file_name, path="", status="pending_upload")
    )


def upload_document(
    file: UploadFile,
    document_repository: DocumentRepository,
    file_system: FileSystem,
    document: Document,
) -> tuple[bytes, Document]:
    """Write the upload once and return those bytes with the stored document."""
    pdf = file.file.read()
    try:
        file.file.seek(0)
    except OSError:
        file.file = BytesIO(pdf)
    directory = Path(settings.DOCUMENTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = str(directory / f"{document.id}.pdf")
    file_system.upload_file(file, path)
    return pdf, document_repository.set_path(document.id, path)


def iterate_pages(paginate: Paginate, document: bytes) -> Iterator[bytes]:
    """Yield each page of the stored PDF, one after another, in page order."""
    for page in paginate(document):  # noqa: UP028
        yield page


async def process_document(
    paginate: Paginate,
    extract_entities: SendsForDetections,
    embed: Embed,
    document_repository: DocumentRepository,
    document_id: uuid.UUID,
    pdf: bytes,
    render_page: Callable[[bytes], bytes] | None = None,
) -> None:
    """Store each page image, then embed each labeled box on that page."""
    render = render_page_image if render_page is None else render_page
    directory = Path(settings.DOCUMENTS_DIR) / str(document_id)
    directory.mkdir(parents=True, exist_ok=True)
    for page_index, page in enumerate(iterate_pages(paginate, pdf)):
        image_path = directory / f"{page_index}.png"
        image_path.write_bytes(render(page))
        document_repository.add_page(
            document_id=document_id,
            page_index=page_index,
            image_path=str(image_path),
        )
        detections = await extract_entities.send(page=page, prompt=ENTITY_PROMPT)
        for box in detections.boxes:
            label = box.label.replace("\x00", "")
            if not label:
                continue
            vector = embed(label.encode())
            document_repository.add_entity(
                document_id=document_id,
                page_index=page_index,
                label=label,
                ymin=box.ymin,
                xmin=box.xmin,
                ymax=box.ymax,
                xmax=box.xmax,
                vector=vector,
            )
    document_repository.update_document_status(str(document_id), "ready")
