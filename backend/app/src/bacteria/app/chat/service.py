"""Composing the agent for one request, and running a turn with it.

Kept out of ``views.py`` so that the wiring can be exercised without an HTTP
client, and out of ``entrypoints/`` because it is logic rather than
configuration: it decides which provider backs the agent and, more importantly,
what the agent is allowed to do.

One tool is registered: ``remember``, which can only *propose* a memory. That is
what makes it registrable at all here. The approval gate exists to answer
"should this call, with these arguments, run now", and over HTTP there is nobody
to ask — the request that would answer arrives after the one that asked. A tool
whose entire effect is "record a suggestion a human will read later" does not
need that question answered, because the human is downstream rather than
upstream. See bacteria's ADR 0017.

Not built:
    Any tool with an effect outside this application. Those still need the
    approval gate to have somebody to ask, which needs a pending-approval
    record, a route that resolves it, and a run that can pause and resume —
    which in turn needs the durable run state the agent lists as missing.
    Registering one now would mean choosing between a service that acts without
    consent and one that always refuses.

    The gate below allows everything, and that is only safe while ``remember``
    is the only tool registered. **Adding a second tool means writing a real
    gate first**, not after.
"""

from bacteria.agent.model.client import ModelClient
from bacteria.agent.model.gemini_client import GeminiClient
from bacteria.agent.model.protocol import SendsMessages
from bacteria.agent.runtime.runtime import RunResult, Runtime
from bacteria.agent.session.protocol import SessionRepository
from bacteria.agent.tools.memory import build_remember_tool
from bacteria.agent.tools.registry import ToolRegistry
from bacteria.app.chat.repository import KnownKeys, SqlSessionRepository
from bacteria.app.chat.tasks import extract_memories_task
from bacteria.app.core import observability
from bacteria.app.core.jobs import get_app
from bacteria.app.graph.tasks import extract_assertions_task

# Suppressed for the same reason as bacteria's own table: the annotation is the
# contract, and a checker inferring the concrete classes from the literal
# reports the wider declared type as a mismatch.
PROVIDERS: dict[str, type[SendsMessages]] = {  # ty: ignore[invalid-assignment]
    "anthropic": ModelClient,
    "gemini": GeminiClient,
}
"""Providers this application can be configured with.

Deliberately a second table rather than a reuse of the agent's own. That one
lives in ``bacteria.agent.interfaces``, which is the agent's composition root for
running standalone, and importing it here would make this application depend on
how the agent's CLI happens to be configured. Two entries duplicated is a
smaller cost than that dependency.
"""


def build_model_client(provider: str, model: str | None = None) -> SendsMessages:
    """Construct the configured client.

    Args:
        model: Which model the client should use, or ``None`` for the client's
            own default. Present because not every model call in this
            application is a conversation — memory extraction fills a small JSON
            schema and wants the cheapest model a provider offers, while sharing
            the provider and its credential. Passed only when set, so the
            clients' defaults stay the single place a default model is named.

    Raises:
        ValueError: Unrecognized provider. Rejected rather than falling back to a
            default, so a typo cannot quietly bill a different vendor.
    """
    try:
        client_cls = PROVIDERS[provider.strip().lower()]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown model provider {provider!r}; expected one of: {known}") from None
    # Suppressed because `SendsMessages` describes `send` and deliberately says
    # nothing about construction -- the agent's ADR 0005 keeps that protocol to
    # one method, so a checker resolving `client_cls(...)` sees `object.__init__`
    # and no `model` parameter. Both concrete clients take one, with their own
    # defaults, which is why this passes the argument only when it is set.
    # Widening the protocol to describe a constructor would trade a suppression
    # here for the provider abstraction layer that ADR rejects.
    return client_cls(model=model) if model else client_cls()  # ty: ignore[unknown-argument]


def build_registry(
    repository: SessionRepository, session_id: str, known: KnownKeys | None = None
) -> ToolRegistry:
    """Build the tools offered for one turn of one session.

    Per turn, not per process, because ``remember`` is bound to the session it
    proposes into. The model supplies the fact; it never supplies the session,
    so it cannot write into a conversation it was not invoked for.

    ``known`` is the vocabulary the tool's ``key`` description is built from.
    Optional so this stays callable without a store that can answer for it, and
    fetched by ``run_turn`` rather than by each entrance, for the reason
    ``run_turn``'s ``extract`` argument gives at length.
    """
    registry = ToolRegistry()
    registry.register(
        build_remember_tool(
            repository,
            session_id,
            confirmed_keys=tuple(known.active) if known else (),
            suggested_keys=tuple(known.proposed) if known else (),
        )
    )
    return registry


def _approver(turn: observability.Turn):
    """Approve every proposed call, and say so where someone can see it.

    Correct *only* because the sole registered tool cannot do anything a human
    would want to stop — it records a suggestion that reaches no model until
    someone activates it. This is a statement about the current registry, not a
    policy. See the module docstring before registering anything else.

    Recording the decision is new and does not close the gap it looks like it
    closes. The agent's ADR 0019 makes a *refusal* structural evidence and leaves
    a *grant* indistinguishable from never having asked; that is a property of
    ``run_meta``, and fixing it is a change to the agent with its own record.
    What this adds is that a gate which currently says yes to everything says so
    out loud, once per call, instead of being invisible because it never
    objects.
    """

    def approve(tool_call) -> bool:
        turn.approval(tool=tool_call.get("name", "unknown"), allowed=True)
        return True

    return approve


def _require_open_queue() -> None:
    """Raise now if this turn will not be able to enqueue when it finishes.

    Procrastinate's ``pool`` property raises :class:`AppNotOpen` when nothing has
    opened the app, and it is touched here purely for that. The check earns its
    place by *when* it runs rather than by what it detects: without it the same
    error arrives after the model has answered and the transcript has been
    written, so a caller that forgot to open the queue pays for a turn, stores
    it, and loses it — and pays again on every retry. Here it costs nothing.

    This is the enforcement half of what ``run_turn``'s ``extract`` argument
    documents. It cannot make a caller open the queue; it can make forgetting
    cheap and immediate instead of expensive and late.
    """
    # Suppressed because `App.connector` is declared as the base type, while
    # `core.jobs.get_app` always constructs a `PsycopgConnector` -- and `pool`,
    # which is where the `AppNotOpen` signal lives, is that subclass's. Narrowing
    # with an `isinstance` would add a branch that cannot be taken and would
    # silently skip the check if it ever were.
    _ = get_app().connector.pool  # ty: ignore[unresolved-attribute]


async def run_turn(
    repository: SqlSessionRepository,
    provider: str,
    session_id: str,
    user_text: str,
    principal: str,
    extract: bool = False,
    build_graph: bool = False,
) -> RunResult:
    """Advance one turn of a conversation.

    The runtime is constructed per call. It holds no state between turns by
    design — everything that survives is in the repository — so a long-lived one
    would buy nothing but the risk of it acquiring some.

    Args:
        principal: Who this turn acts for. Required rather than defaulted, and
            required *here* rather than resolved at each entrance, because the
            agent's ADR 0019 lists the identity a run acted under as unrecorded
            and says it belongs to the host. A default would let an entrance
            omit it and produce runs attributed to nobody, which is the failure
            the ``extract`` argument below describes in its own terms.

            It reaches the trace and not yet ``run_meta``. Putting it in the
            transcript means widening what the agent stores, which is that
            package's decision to make.
        build_graph: Whether to queue graph extraction over what this turn
            wrote — the relationships between things said, rather than the facts
            worth telling a model later.

            Separate from ``extract`` rather than folded into it. They are two
            model calls with two costs and two failure modes, and a deployment
            wanting suggested facts reviewed by a person does not thereby want a
            graph built. One argument would make turning either on a decision
            about both, which is the coupling the two watermarks exist to avoid.
        extract: Whether to queue memory extraction over what this turn wrote.

            An argument rather than a settings lookup, so configuration stays at
            the edge and a caller can always be read to see what it asked for.

            It lives *here* rather than in the route, and that is the point of
            the parameter existing at all. The enqueue was in
            ``views.take_turn`` first, which made extraction a property of one
            entrance: a second way to run a turn — this repository's admin CLI,
            the planned audio path, a bot — would write a transcript and
            silently never extract from it, with nothing failing and no
            proposals ever appearing. That is the drift
            :mod:`bacteria.app.ingestion.tasks` avoids by having the deferred
            path call the same ``ingest`` the inline one does, and the same
            reasoning applies to a trigger.

            **Passing ``True`` obliges the caller to have opened the job queue**
            — ``async with register_tasks().open_async()`` — because enqueueing
            needs a pool and this function does not own one. Nothing here can
            check it, and the failure is late and expensive: the model has
            answered and the transcript is written before ``AppNotOpen`` is
            raised, so the turn is charged for and lost. The API opens it in its
            lifespan and the admin CLI in its command; a third caller has to do
            the same. This obligation is the cost of the trigger living here
            rather than at each entrance, and it is the smaller cost.
    """
    if extract or build_graph:
        _require_open_queue()

    # Fetched here rather than by each entrance, and the concrete repository is
    # in the signature for it. `known_keys` is deliberately off the agent's
    # protocol -- no turn depends on it, and a second host should not owe it --
    # but both proposers converging on one name for a fact is a property of this
    # application, so the one function every turn goes through is where it
    # belongs. At an entrance it would be a step the next entrance forgets.
    known = await repository.known_keys(session_id)

    # The root every other span in this turn hangs from, and the only place a
    # trace and the transcript name the same thing. Around the whole turn rather
    # than the model call, so a turn that raised is still a span -- the failure
    # path is where "how long before it gave up" is asked most.
    with observability.turn_span(session_id=session_id, principal=principal) as turn:
        runtime = Runtime(model_client=build_model_client(provider), session_store=repository)
        result = await runtime.run_turn(
            session_id,
            user_text,
            tool_registry=build_registry(repository, session_id, known),
            approve=_approver(turn),
        )
        turn.records(result.run_id)

    # Both after the turn, so each job sees the transcript this turn wrote rather
    # than the one before it. A turn that raised never reaches here and never
    # enqueues, which loses nothing: neither watermark moved, so the next
    # successful turn reads that turn's messages too.
    if extract:
        await extract_memories_task.defer_async(session_id=session_id)

    # Enqueued independently rather than from inside the other job. They read the
    # same slice and fail separately, and chaining them would make a graph
    # extraction that returned unusable JSON cost a memory proposal its run — or,
    # the other way round, make the graph silently stop being built the day
    # someone turned memory extraction off.
    if build_graph:
        await extract_assertions_task.defer_async(session_id=session_id)

    return result
