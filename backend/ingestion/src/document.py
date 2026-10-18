from asyncio import Protocol
import uuid

from sqlmodel import SQLModel


class Document(SQLModel):
    id: uuid.UUID
    status: str


class DocumentRepository(Protocol):
    def create_document(self, document: Document) -> Document:
        ...

    def get_document_by_id(self, document_id: str) -> Document:
        ...

    def update_document_status(self, document_id: str, status: str) -> None:
        ...
