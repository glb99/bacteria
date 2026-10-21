import importlib.util
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.api.services.document_repository import SqlDocumentRepository
from app.models import Document

_CLI_PATH = Path(__file__).resolve().parents[3] / "cli" / "cli.py"
_SPEC = importlib.util.spec_from_file_location("bacteria_cli", _CLI_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_CLI = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CLI)
load_stored_entities = _CLI.load_stored_entities


def test_load_stored_entities_reads_document_entity_rows(tmp_path) -> None:
    database_path = tmp_path / "docs.db"
    database_url = "sqlite:///" + database_path.as_posix()
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
            image_path="documents/plant-2.png",
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
    assert entities[0].image_path == "documents/plant-2.png"
