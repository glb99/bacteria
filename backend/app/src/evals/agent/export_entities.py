"""Write the stored entity rows to the eval fixture.

Run once while Postgres is available:

    uv run --directory backend/app python src/evals/agent/export_entities.py
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlmodel import Session

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "entities.json"


def export_entities(destination: Path) -> int:
    """Read every ``document_entity`` row and write the eval snapshot.

    Returns the number of rows written. Image paths are not stored; the eval
    points each row at ``pages/{page_index}.png``.
    """
    load_dotenv(find_dotenv(usecwd=True))
    from app.api.services.document_repository import SqlDocumentRepository
    from app.core.db import engine

    with Session(engine) as session:
        repository = SqlDocumentRepository(session)
        rows = [
            {
                "document_id": str(row.document_id),
                "page_index": row.page_index,
                "vector": list(row.vector),
            }
            for row in repository.list_entities()
        ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(rows), encoding="utf-8")
    return len(rows)


def main() -> None:
    count = export_entities(FIXTURE_PATH)
    if count == 0:
        raise SystemExit("exported 0 entity rows")


if __name__ == "__main__":
    main()
