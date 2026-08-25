"""Graph extraction as a background job.

A thin shell, matching :mod:`bacteria.app.chat.tasks`: it opens a session, builds
a client, and calls :func:`bacteria.app.graph.extraction.extract_assertions`. The
logic lives there so a test can drive it with a fake client and no queue, which
is the only way the interesting behaviour is reachable at all.

Deferred rather than inline, and for the same reason as its sibling: extraction
is a second model call, and running it inside the turn would add its latency to
every reply for a result the caller never sees. The turn's own transaction is the
right place to *enqueue* it, because a turn that committed a transcript nobody
extracts from is the silent gap this queue exists to prevent.

**A second job rather than more work inside the first.** Both read the same
transcript slice and could share a run, and they are separate because they fail
and are retried independently: a graph extraction that returns unusable JSON must
not cost a memory proposal its run, and a prompt change that justifies re-reading
one does not justify re-reading the other. That is the same argument the two
watermarks make, and it stops being true the moment one of them is enqueued only
when the other succeeds.

Only the ``session_id`` travels in the arguments. The transcript is already in
the database and the job can read it; copying a conversation into the jobs table
would duplicate it into a second place with its own retention question, and that
copy would be stale the moment the next turn landed.
"""

import logging
from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.core.db import get_engine
from bacteria.app.core.jobs import get_app
from bacteria.app.core.settings import get_settings
from bacteria.app.graph.extraction import extract_assertions

logger = logging.getLogger(__name__)


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

    # Imported inside the function for the reason `chat/tasks.py` gives about its
    # own: `chat.service` enqueues this task and this task builds a client from
    # `chat.service`'s provider table, so a module-level import in both
    # directions closes a cycle.
    from bacteria.app.chat.service import build_model_client

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
