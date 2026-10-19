from app.core.file_system import FileSystem
from app.models import Document
from fastapi import UploadFile

from SQLModel import Session
from ingestion.document import DocumentRepository, Document


def validate_document(
    file_name: str,
    document_repository: DocumentRepository,
) -> Document:
    """
    Validate the document before uploading.
    """
    document = document_repository.get_by_file_name(file_name=file_name)

    if document:
        raise MIDPException(
            code=400,
            error=f"Document with file name '{file_name}' already exists.",
        )

    document = Document(
        status="pending_upload"
    )

    document = document_repository.create_document(document)
    return document


def upload_document(
    file: UploadFile,
    document_repository: DocumentRepository,
    file_system: FileSystem,
    document: Document,
) -> Document:
    """
    Upload a document to the file system and update its status in the database.
    """
    file_system.upload_file(file: file)
    uploaded_document = Document(
        state="uploaded"
    )
    document_repository.update(
        document=uploaded_document
    )


def
