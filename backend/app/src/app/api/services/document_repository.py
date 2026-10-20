import uuid

from sqlmodel import Session, select

from app.models import Document, DocumentEntity


class SqlDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_document(self, document: Document) -> Document:
        self._session.add(document)
        self._session.commit()
        self._session.refresh(document)
        return document

    def get_document_by_id(self, document_id: str) -> Document | None:
        return self._session.get(Document, uuid.UUID(document_id))

    def get_by_file_name(self, file_name: str) -> Document | None:
        statement = select(Document).where(Document.file_name == file_name)
        return self._session.exec(statement).first()

    def set_path(self, document_id: uuid.UUID, path: str) -> Document:
        document = self._session.get(Document, document_id)
        if document is None:
            raise LookupError(str(document_id))
        document.path = path
        self._session.add(document)
        self._session.commit()
        self._session.refresh(document)
        return document

    def update_document_status(self, document_id: str, status: str) -> None:
        document = self.get_document_by_id(document_id)
        if document is None:
            raise LookupError(document_id)
        document.status = status
        self._session.add(document)
        self._session.commit()

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
        self._session.add(
            DocumentEntity(
                document_id=document_id,
                page_index=page_index,
                label=label.replace("\x00", ""),
                y_min=ymin,
                x_min=xmin,
                y_max=ymax,
                x_max=xmax,
                vector=vector,
            )
        )
        self._session.commit()
