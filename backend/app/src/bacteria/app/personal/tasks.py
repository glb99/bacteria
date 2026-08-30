"""The personal domain's background jobs: memory, and claims.

A thin shell, matching :mod:`bacteria.app.ingestion.tasks`: it opens a session,
builds a client, and calls :func:`bacteria.app.personal.memory_extraction.extract_memories`.
The logic lives there so that a test can drive it with a fake client and no
queue, which is the only way the interesting behaviour is reachable at all.

Deferred rather than inline, and that is the decision worth stating. Extraction
is a second model call, and running it inside the turn would add its latency to
every reply for a result the caller never sees — the proposals it writes are read
later, by a person, through a different route. The turn's own transaction is the
right place to *enqueue* it, because a turn that committed a transcript nobody
extracts from is the silent gap this queue exists to prevent.

Only the ``session_id`` travels in the arguments. The transcript is already in
the database and the job can read it; copying a conversation into the jobs table
would duplicate it into a second place with its own retention question, and that
copy would be stale the moment the next turn landed.

**Two jobs rather than one, now that they share a module.** Both read the same
transcript slice and could share a run. They are separate because they fail and
are retried independently: a claim extraction that returns unusable JSON must not
cost a memory proposal its run, and a prompt change that justifies re-reading one
does not justify re-reading the other. That is the same argument the two
watermarks make, and it stops being true the moment one is enqueued only when the
other succeeds.
"""

import logging
from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.core.db import get_engine
from bacteria.app.core.jobs import get_app
from bacteria.app.core.model_client import build_model_client
from bacteria.app.core.settings import get_settings
from bacteria.app.personal.claim_extraction import extract_assertions
from bacteria.app.personal.memory_extraction import extract_memories

logger = logging.getLogger(__name__)


@get_app().task(name="extract_memories", queue="chat", retry=2)
async def extract_memories_task(session_id: str) -> dict[str, int]:
    """Read what is new in a session and propose memories from it.

    **Retries are configured here and deliberately are not on ingestion**, which
    is the contrast worth understanding before copying either. Ingestion is not
    idempotent — it detects duplicates only within a batch, so a retried job
    stores every record twice. This job is idempotent by construction: proposals
    are keyed by ``(source, key)`` and overwrite, and the watermark only moves
    forward, so a retry rewrites its own suggestions and reads the same slice.
    That is the property the agent's ADR 0017 predicted would make a background
    proposer safe to retry, and it holds.

    Returns counts rather than the proposed facts. A task's return value is
    stored in the jobs table, and putting the facts there would copy them into a
    second place that nothing reads and nothing expires.
    """
    settings = get_settings()
    client = build_model_client(settings.model_provider, model=settings.memory_extraction_model)

    async with AsyncSession(get_engine()) as db:
        result = await extract_memories(
            db,
            client,
            session_id=session_id,
            max_proposals=settings.memory_extraction_max_proposals,
        )

    logger.info(
        "extracted memories",
        extra={
            "session_id": session_id,
            "examined": result.examined,
            "proposed": result.proposed,
            "dropped": result.dropped,
            "through_seq": result.through_seq,
        },
    )
    return {
        "examined": result.examined,
        "proposed": result.proposed,
        "dropped": result.dropped,
        "through_seq": result.through_seq,
    }


@get_app().task(name="extract_assertions", queue="chat", retry=2)
async def extract_assertions_task(session_id: str) -> dict[str, int]:
    """Read what is new in a session and record what it says relates to what.

    **Retries are safe here, and the reason is not the one that makes the memory
    extractor safe.** That job is idempotent because proposals are keyed by
    ``(source, key)`` and overwrite. This one is idempotent because an assertion
    id is derived from the claim and the run's timestamp, and recording an
    assertion that already exists is a no-op — so a retry that re-reads the same
    slice lands exactly where the first attempt did.

    The timestamp is taken here rather than inside the extractor, so everything
    one run records shares a recorded time. Two claims from one slice that
    disagreed by milliseconds would sort into an order nothing chose, and
    ``believed_at`` would have a moment where one existed and the other did not.

    Returns counts rather than the claims. A task's return value is stored in the
    jobs table, and putting them there would copy the content into a second place
    that nothing reads and nothing expires.
    """
    settings = get_settings()

    client = build_model_client(settings.model_provider, model=settings.graph_extraction_model)

    async with AsyncSession(get_engine()) as db:
        result = await extract_assertions(
            db,
            client,
            session_id=session_id,
            max_assertions=settings.graph_extraction_max_assertions,
            now=datetime.now(timezone.utc),
        )
        await db.commit()

    logger.info(
        "extracted assertions",
        extra={
            "session_id": session_id,
            "examined": result.examined,
            "recorded": result.recorded,
            "dropped": result.dropped,
            "duplicates": result.duplicates,
            "conflicts": result.conflicts,
            "through_seq": result.through_seq,
        },
    )
    return {
        "examined": result.examined,
        "recorded": result.recorded,
        "dropped": result.dropped,
        "duplicates": result.duplicates,
        "conflicts": result.conflicts,
        "through_seq": result.through_seq,
    }
