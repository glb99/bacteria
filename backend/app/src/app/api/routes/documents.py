import uuid

from fastapi import APIRouter, HTTPException, UploadFile

from app.api.deps import (
    DocumentRepositoryDep,
    EmbedDep,
    ExtractEntitiesDep,
    LocalFilesystemDep,
    ModelClientDep,
    PaginateDep,
)
from app.api.services import document_service
from app.models import DocumentStatus

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    path="/uploaded",
    response_model=DocumentStatus,
)
async def upload_document(
    document_repository: DocumentRepositoryDep,
    file_system: LocalFilesystemDep,
    paginate: PaginateDep,
    entity_extractor: ExtractEntitiesDep,
    embedder: EmbedDep,
    model_client: ModelClientDep,
    file: UploadFile,
) -> DocumentStatus:
    document = document_service.validate_document(
        file_name=file.filename or "",
        document_repository=document_repository,
    )
    pdf, document = document_service.upload_document(
        file=file,
        document_repository=document_repository,
        file_system=file_system,
        document=document,
    )
    await document_service.process_document(
        paginate=paginate,
        extract_entities=entity_extractor,
        model_client=model_client,
        embed=embedder,
        document_repository=document_repository,
        document_id=document.id,
        pdf=pdf,
    )
    return DocumentStatus(id=document.id, status="ready")


@router.get("/{document_id}", response_model=DocumentStatus)
def read_document(
    document_id: uuid.UUID,
    document_repository: DocumentRepositoryDep,
) -> DocumentStatus:
    document = document_repository.get_document_by_id(str(document_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentStatus(id=document.id, status=document.status)
