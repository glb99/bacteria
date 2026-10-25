from sqlmodel import Session, SQLModel, create_engine

from app.agent.retriever import EmbeddingPageRetriever
from app.api.services.document_repository import SqlDocumentRepository
from app.cli import cli as _CLI
from app.models import Document

load_stored_entities = _CLI.load_stored_entities


def test_load_stored_entities_reads_document_entity_rows(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "docs.db"
    database_url = "sqlite:///" + database_path.as_posix()
    documents_dir = tmp_path / "documents"
    image_path = documents_dir / "plant-2.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"page image")
    monkeypatch.setattr(_CLI, "_LOCAL_DOCUMENTS_DIR", documents_dir, raising=False)
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(
        engine,
        tables=[
            SQLModel.metadata.tables["document"],
            SQLModel.metadata.tables["document_entity"],
            SQLModel.metadata.tables["page"],
        ],
    )
    with Session(engine) as session:
        repository = SqlDocumentRepository(session)
        document = repository.create_document(
            Document(file_name="plant.pdf", path="documents/plant.pdf", status="ready")
        )
        repository.add_page(
            document_id=document.id,
            page_index=2,
            image_path="/data/documents/plant-2.png",
        )
        repository.add_entity(
            document_id=document.id,
            page_index=2,
            label="Pump",
            ymin=1,
            xmin=2,
            ymax=3,
            xmax=4,
            vector=[0.25, 0.75],
        )
        document_id = str(document.id)
    engine.dispose()

    entities = load_stored_entities(database_url)

    assert len(entities) == 1
    assert entities[0].document_id == document_id
    assert entities[0].page_index == 2
    assert entities[0].vector == [0.25, 0.75]
    assert entities[0].image_path == str(image_path)

    retriever = EmbeddingPageRetriever(
        embed=lambda _: [0.25, 0.75],
        entities=entities,
    )
    assert retriever.select(query="pump", limit=1) == [b"page image"]
