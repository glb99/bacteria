import json
from pathlib import Path

import pytest

from app.agent.retriever import StoredEntity

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "entities.json"
_PAGES_DIR = Path(__file__).parent / "pages"


@pytest.fixture(scope="module")
def stored_entities() -> list[StoredEntity]:
    """The frozen corpus, with each row pointed at the local page image."""
    rows = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [
        StoredEntity(
            document_id=row["document_id"],
            page_index=row["page_index"],
            vector=row["vector"],
            image_path=str(_PAGES_DIR / f"{row['page_index']}.png"),
        )
        for row in rows
    ]
