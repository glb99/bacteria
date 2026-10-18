from app.api.deps import DocumentRepositoryDep, ScopedSessionDep
from app.api.services import document_service
from app.core.file_system import LocalFileSystem
from app.models import UploadedDocument
from fastapi import APIRouter, UploadFile
from app.core.config import settings

router = APIRouter(prefix="/items", tags=["items"])


@router.post(
    path="/uploaded",
    response_model=UploadedDocument,
)
def upload_document(
    document_repository: DocumentRepositoryDep,
    file_system: LocalFileSystem,
    file: UploadFile,
):
    document = None
    try:
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
        if document.channel == ChannelType.FLOW:
            send_document_message(
                document=DocumentBase(**document.__dict__),
                sqs=get_sqs_client(),
                queue_url=settings.DOCUMENTS_TO_DETECT_QUEUE,
                delay=settings.DOCUMENTS_QUEUE_DELAY,
            )
        return document
    except (MIDPException, HTTPException) as e:
        if document:
            document_service.save_project_document_error(
                session=session,
                project_id=project_id,
                document_id=document.id,
                exception=e,
            )
        raise HTTPException(status_code=e.code, detail=e.error)
