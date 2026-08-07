"""Ingestion over HTTP, against a real database.

Nothing is faked here — there is no model in this path — so these exercise the
route, the pipeline, and the repository together.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.auth.service import issue_key
from fastpaip.core.db import create_tables, session_scope
from fastpaip.ingestion.models import IngestedRecord, IngestionBatch, RejectedRecord
from fastpaip.views import create_app, lifespan_running


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(name="db_engine")
def _db_engine():
    return create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(name="token")
async def _token(db_engine, client):
    """An API key for the principal these tests act as.

    Depends on `client` so the schema exists first: tables are built in the
    app's lifespan, which runs when TestClient starts.
    """
    async with AsyncSession(db_engine) as session:
        return await issue_key(session, principal_id="tester", label="tests")


@pytest.fixture(name="client")
def _client(db_engine):
    async def _create_tables():
        await create_tables(db_engine)

    async def _test_session():
        async with AsyncSession(db_engine) as session:
            yield session

    app = create_app(lifespan=lifespan_running(_create_tables))
    app.dependency_overrides[session_scope] = _test_session
    with TestClient(app) as client:
        yield client


async def test_a_clean_batch_is_stored(client, token, db_engine):
    response = client.post(
        "/ingestion/batches",
        headers=auth(token),
        json={"source": "crm", "records": [{"external_id": "1", "name": "Ada"}]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"] == []

    async with AsyncSession(db_engine) as db:
        stored = (await db.exec(select(IngestedRecord))).all()
        assert [r.external_id for r in stored] == ["1"]


async def test_rejections_are_returned_in_full_not_counted(client, token):
    """A caller must be able to find and fix the records that failed.

    "42 of 50 accepted" is not actionable — the eight are unidentifiable, and
    the reason is the only part that says what to change.
    """
    response = client.post(
        "/ingestion/batches",
        headers=auth(token),
        json={
            "source": "crm",
            "records": [{"external_id": "1", "name": "Ada"}, {"name": "nameless"}],
        },
    )

    body = response.json()
    assert body["accepted"] == 1
    assert len(body["rejected"]) == 1
    assert "external_id" in body["rejected"][0]["reason"]
    assert body["rejected"][0]["payload"] == {"name": "nameless"}
    assert body["rejected"][0]["index"] == 1


async def test_rejected_records_are_persisted_alongside_the_batch(client, token, db_engine):
    """The rejection outlives the response that reported it.

    A caller who ignored the response, or a job that ran unattended, still needs
    the answer to "what did we drop and why" to exist somewhere.
    """
    client.post(
        "/ingestion/batches",
        headers=auth(token),
        json={"source": "crm", "records": [{"name": "nameless"}]},
    )

    async with AsyncSession(db_engine) as db:
        rejected = (await db.exec(select(RejectedRecord))).all()
        assert len(rejected) == 1
        assert rejected[0].payload == {"name": "nameless"}


async def test_a_batch_records_its_own_counts(client, token, db_engine):
    client.post(
        "/ingestion/batches",
        headers=auth(token),
        json={
            "source": "crm",
            "records": [
                {"external_id": "1", "name": "Ada"},
                {"external_id": "2", "name": "Grace"},
                {"name": "nameless"},
            ],
        },
    )

    async with AsyncSession(db_engine) as db:
        batch = (await db.exec(select(IngestionBatch))).one()
        assert (batch.accepted_count, batch.rejected_count) == (2, 1)
        assert batch.source == "crm"


async def test_a_wholly_invalid_batch_is_still_recorded(client, token, db_engine):
    """Nothing valid is the case where the evidence matters most.

    Not storing it would mean the only batch nobody can explain afterwards is
    the one that went entirely wrong. The request succeeds -- the submission was
    received and answered -- and the batch row carries the reasons.
    """
    response = client.post(
        "/ingestion/batches",
        headers=auth(token),
        json={"source": "crm", "records": [{"name": "nameless"}]},
    )

    assert response.status_code == 201
    assert response.json()["batch_id"] is not None

    async with AsyncSession(db_engine) as db:
        batch = (await db.exec(select(IngestionBatch))).one()
        assert (batch.accepted_count, batch.rejected_count) == (0, 1)
        assert len((await db.exec(select(RejectedRecord))).all()) == 1


async def test_an_oversized_batch_is_refused_by_validation(client, token):
    """The inline-execution limit is enforced before any work starts.

    The bound exists because ingestion runs in the request that submits it,
    so it has to be a rejection rather than something discovered partway
    through.
    """
    records = [{"external_id": str(i), "name": f"n{i}"} for i in range(501)]

    response = client.post(
        "/ingestion/batches", headers=auth(token), json={"source": "crm", "records": records}
    )

    assert response.status_code == 422


async def test_an_empty_batch_is_refused(client, token):
    response = client.post(
        "/ingestion/batches", headers=auth(token), json={"source": "crm", "records": []}
    )

    assert response.status_code == 422


async def test_a_stored_rejection_keeps_its_position(client, token, db_engine):
    """The index outlives the response, so the record stays identifiable.

    A caller that lost the response, or a deferred job nobody watched, still
    needs to know which of the submitted records failed.
    """
    client.post(
        "/ingestion/batches",
        headers=auth(token),
        json={
            "source": "crm",
            "records": [
                {"external_id": "1", "name": "Ada"},
                {"name": "nameless"},
                {"name": "nameless"},
            ],
        },
    )

    async with AsyncSession(db_engine) as db:
        stored = (await db.exec(select(RejectedRecord).order_by(RejectedRecord.id))).all()
        assert [r.source_index for r in stored] == [1, 2]
