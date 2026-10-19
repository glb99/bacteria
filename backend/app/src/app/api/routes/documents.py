from app.api.deps import DocumentRepositoryDep, ScopedSessionDep
from app.api.services import document_service
from app.core.file_system import LocalFileSystem
from app.models import UploadedDocument
from fastapi import APIRouter, UploadFile
from app.core.config import settings
from ingestion.embedder import Embed
from ingestion.entity_extractor import EntityExtractor
from ingestion.paginator import Paginate

router = APIRouter(prefix="/items", tags=["items"])


@router.post(
    path="/uploaded",
    response_model=UploadedDocument,
)
def upload_document(
    document_repository: DocumentRepositoryDep,
    file_system: LocalFileSystem,
    file: UploadFile,
    paginate: Paginate,
    entity_extractor: EntityExtractor,
    embedder: Embed,
):
    document = None
    file_name = file.filename
    document = document_service.validate_document(
        file_name=file_name,
        document_repository=document_repository
    )
    document = document_service.upload_document(
        file=file,
        document_repository=document_repository,
        file_system=file_system,
        document=document,
    )
