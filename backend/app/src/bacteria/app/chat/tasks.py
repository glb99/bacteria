"""Memory extraction as a background job.

A thin shell, matching :mod:`bacteria.app.ingestion.tasks`: it opens a session,
builds a client, and calls :func:`bacteria.app.chat.extraction.extract_memories`.
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
"""

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.chat.extraction import extract_memories
from bacteria.app.chat.service import build_model_client
from bacteria.app.core.db import get_engine
from bacteria.app.core.jobs import get_app
from bacteria.app.core.settings import get_settings

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
