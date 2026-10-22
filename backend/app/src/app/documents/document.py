import uuid
from typing import Protocol

from sqlmodel import SQLModel


class Document(SQLModel):
    id: uuid.UUID
    file_name: str = ""
    path: str = ""
    status: str


class DocumentRepository(Protocol):
    def create_document(self, document: Document) -> Document:
        ...

    def get_document_by_id(self, document_id: str) -> Document | None:
        ...

    def get_by_file_name(self, file_name: str) -> Document | None:
        ...

    def set_path(self, document_id: uuid.UUID, path: str) -> Document:
        ...

    def update_document_status(self, document_id: str, status: str) -> None:
        ...

    def add_page(
        self,
        document_id: uuid.UUID,
        page_index: int,
        image_path: str,
    ) -> None:
        ...

    def add_entity(
        self,
        document_id: uuid.UUID,
        page_index: int,
        label: str,
        ymin: int,
        xmin: int,
        ymax: int,
        xmax: int,
        vector: list[float],
    ) -> None:
        ...
