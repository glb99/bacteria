import asyncio
import uuid
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from ingestion.entity_extractor import Box, Detections
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.routes.documents import read_document, upload_document
from app.api.services.document_repository import SqlDocumentRepository
from app.api.services.document_service import process_document, validate_document
from app.core.config import settings
from app.models import Document, DocumentEntity, DocumentStatus


def _box(label: str) -> Box:
    return Box(label=label, ymin=1, xmin=2, ymax=3, xmax=4)


class _Repository:
    def __init__(self) -> None:
        self.entities: list[dict[str, object]] = []
        self.status: tuple[str, str] | None = None

    def add_entity(self, **kwargs: object) -> None:
        self.entities.append(kwargs)

    def update_document_status(self, document_id: str, status: str) -> None:
        self.status = (document_id, status)


class _Client:
    def __init__(self) -> None:
        self.pages: list[bytes] = []

    async def send(self, page: bytes, prompt: str) -> Detections:
        self.pages.append(page)
        if page == b"one":
            return Detections(boxes=[_box("Pump")])
        return Detections(boxes=[_box(""), _box("Valve")])


def test_process_document_drops_nul_bytes_from_labels() -> None:
    async def extract(_model_client: object, _page: bytes, _prompt: str) -> Detections:
        return Detections(boxes=[_box("re\x00identification")])

    repository = _Repository()
    embedded: list[bytes] = []

    asyncio.run(
        process_document(
            paginate=lambda doc: iter((doc,)),
            extract_entities=extract,
            model_client=object(),
            embed=embedded.append,
            document_repository=repository,
            document_id=uuid.uuid4(),
            pdf=b"stored-pdf",
        )
    )

    assert embedded == [b"reidentification"]
    assert repository.entities[0]["label"] == "reidentification"


def test_process_document_handles_pages_in_order() -> None:
    pulled: list[str] = []
    extracts = 0

    def paginate(doc: bytes):
        assert doc == b"stored-pdf"
        pulled.append("first")
        yield b"one"
        assert extracts == 1
        pulled.append("second")
        yield b"two"

    async def extract(model_client: _Client, page: bytes, prompt: str) -> Detections:
        nonlocal extracts
        extracts += 1
        return await model_client.send(page, prompt)

    client = _Client()
    repository = _Repository()
    embedded: list[bytes] = []

    asyncio.run(
        process_document(
            paginate=paginate,
            extract_entities=extract,
            model_client=client,
            embed=embedded.append,
            document_repository=repository,
            document_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            pdf=b"stored-pdf",
        )
    )

    assert pulled == ["first", "second"]
    assert client.pages == [b"one", b"two"]
    assert embedded == [b"Pump", b"Valve"]
    assert [entity["page_index"] for entity in repository.entities] == [0, 1]
    assert repository.entities[0]["label"] == "Pump"
    assert repository.entities[0]["xmin"] == 2
    assert repository.status == (
        "11111111-1111-1111-1111-111111111111",
        "ready",
    )


def test_repository_stores_the_document_and_its_entities() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(
        engine,
        tables=[
            SQLModel.metadata.tables["document"],
            SQLModel.metadata.tables["document_entity"],
        ],
    )
    with Session(engine) as session:
        repository = SqlDocumentRepository(session)
        created = repository.create_document(
            Document(file_name="plant.pdf", path="", status="pending_upload")
        )
        stored = repository.set_path(created.id, "documents/plant.pdf")
        repository.add_entity(
            document_id=stored.id,
            page_index=0,
            label="Pump",
            ymin=1,
            xmin=2,
            ymax=3,
            xmax=4,
            vector=[0.5],
        )
        repository.update_document_status(str(stored.id), "ready")

        assert repository.get_by_file_name(file_name="plant.pdf").status == "ready"
        entity = session.exec(select(DocumentEntity)).one()
        assert entity.page_index == 0
        assert entity.label == "Pump"
        assert entity.vector == [0.5]


class _RouteRepository:
    def __init__(self) -> None:
        self.document: Document | None = None
        self.ready = False

    def get_by_file_name(self, file_name: str) -> Document | None:
        if self.document and self.document.file_name == file_name:
            return self.document
        return None

    def create_document(self, document: Document) -> Document:
        self.document = document
        return document

    def set_path(self, document_id: uuid.UUID, path: str) -> Document:
        assert self.document is not None
        self.document.path = path
        return self.document

    def add_entity(self, **kwargs: object) -> None:
        return None

    def update_document_status(self, document_id: str, status: str) -> None:
        assert self.document is not None
        self.document.status = status
        self.ready = True

    def get_document_by_id(self, document_id: str) -> Document | None:
        return self.document


class _FileSystem:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def upload_file(self, file: UploadFile, path: str) -> str:
        assert file.file.read() == b"%PDF"
        self.paths.append(path)
        return path


def test_upload_returns_ready_only_after_processing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DOCUMENTS_DIR", str(tmp_path))
    repository = _RouteRepository()
    processed: list[bytes] = []

    async def extract(model_client: object, page: bytes, prompt: str) -> Detections:
        assert model_client is not None
        assert prompt
        assert repository.ready is False
        processed.append(page)
        return Detections(boxes=[_box("Pump")])

    def paginate(doc: bytes):
        yield doc

    result = asyncio.run(
        upload_document(
            document_repository=repository,
            file_system=_FileSystem(),
            paginate=paginate,
            entity_extractor=extract,
            embedder=lambda entity: [float(len(entity))],
            model_client=object(),
            file=UploadFile(file=BytesIO(b"%PDF"), filename="plant.pdf"),
        )
    )

    assert processed == [b"%PDF"]
    assert result == DocumentStatus(id=repository.document.id, status="ready")
    assert repository.ready is True


def test_read_document_returns_only_id_and_status() -> None:
    repository = _RouteRepository()
    repository.document = Document(
        file_name="plant.pdf", path="secret.pdf", status="ready"
    )

    result = read_document(repository.document.id, repository)

    assert set(result.model_dump()) == {"id", "status"}
    assert result.status == "ready"


def test_duplicate_file_name_is_rejected() -> None:
    repository = _RouteRepository()
    repository.document = Document(file_name="plant.pdf", path="", status="ready")

    with pytest.raises(HTTPException) as raised:
        validate_document("plant.pdf", repository)

    assert raised.value.status_code == 400
