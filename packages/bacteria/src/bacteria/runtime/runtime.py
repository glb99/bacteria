"""Advances one turn from user input to committed result.

The runtime is a conductor, not a performer. It decides what happens in what
order and delegates every step: context assembly to
:mod:`bacteria.context.assembly`, the model call to a
:class:`~bacteria.model.protocol.SendsMessages` implementation, tool execution
to :mod:`bacteria.tools.execution`, and every state write to a
:class:`~bacteria.session.protocol.SessionRepository`. It reimplements none of
them.
When that boundary erodes — when the runtime starts formatting prompts or
touching the transcript directly — the system stops having answerable ownership
questions, and every one of those decisions becomes a search of the orchestration
path rather than a read of one module.

Three vocabulary items worth keeping distinct, because they are routinely
merged and mean different things:

- a **run** is one execution — here, one turn.
- the **runtime** is the engine that advances runs. This module.
- a **workflow** is not an execution at all; it is the *shape* a run is allowed
  to take — its states, its wait points, its resumption rules. Not built.

Invariant: a run leaves evidence whether or not it succeeds. Any exception
inside a turn commits everything accumulated so far, tagged with a
``run_error`` item, before re-raising. A failed run that commits nothing is the
worst of both outcomes: the user's message is gone, the failure is unexplained,
and the only record is a stack trace in a terminal someone has since closed.
This is why evidence accumulates as the turn progresses rather than being
assembled at the end from results — the natural implementation loses exactly the
runs worth investigating.

Invariant: within a run, a step executes at most once. :class:`StepTracker`
refuses a repeated step id rather than trusting that no code path loops back.
This is cheap and catches the one bug class that would be most expensive here —
a retry silently re-running a side effect that already succeeded.

Not built:
    Durability. Run state lives in local variables for the length of one call.
    There is no run store, no checkpointing, no replay, and no resume after a
    crash — a process that dies mid-turn loses the turn. :class:`StepTracker`
    gives idempotency *within* a run, which is a different and much weaker
    property than idempotency across restarts. Making runs durable means
    persisting ``run_id`` and the executed-step set after each step, and
    reloading them on resume; the session store's persistence gap has to be
    closed first, since a resumed run needs the state it was operating on.
    Worth doing deliberately rather than approximately: retry, replay, resume,
    and idempotency are four different properties, and a system that persists a
    checkpoint while getting step boundaries wrong resumes into a state where a
    side effect runs twice — silently, and with confidence it has not earned.

    Multi-round tool loops. Exactly one round of tool execution happens per
    turn: model, tools, model, done. A model that wants a second round after
    seeing results cannot have one — its follow-up response is the final answer.
    This bounds a turn's cost to two model calls and makes it knowable in
    advance, and it is also the ceiling on what this agent can do. Lifting it is
    confined to ``run_turn`` but is not merely a ``while`` loop: the round cap,
    the cost budget, and the policy for partial failure after earlier rounds
    already had side effects all have to be decided at the same time.

    Run resolution. Every turn starts a new run. Deciding whether an incoming
    event resumes an existing run, appends to it, or forks a new one is a
    control-plane question that only has content once runs can be interrupted
    or overlap.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from bacteria.context.assembly import AssembledContext, assemble_context
from bacteria.model.protocol import ModelResponse, SendsMessages, ToolCall
from bacteria.session.protocol import SessionRepository
from bacteria.session.store import SessionState, TranscriptItem
from bacteria.tools.execution import Approve, ToolExecutionError, ToolResult, execute_tool_call
from bacteria.tools.registry import ToolRegistry


class StepAlreadyExecutedError(Exception):
    """A step was about to run a second time within the same run.

    Always a bug in the runtime's own control flow, never something a caller
    can cause. Raised loudly instead of skipping the repeat, because a skipped
    duplicate would return ``None`` where a result was expected and fail
    somewhere less informative.
    """


class StepTracker:
    """Remembers which steps have run, so none can run twice in one run.

    Deliberately minimal: a set of ids, no persistence, no results cache. It
    provides idempotency *within* a run and claims nothing beyond that — after
    the run returns, the tracker is discarded along with everything it knew.
    Durable idempotency is a different mechanism and is not built.
    """

    def __init__(self) -> None:
        self._executed: set[str] = set()

    def has_run(self, step_id: str) -> bool:
        """Whether ``step_id`` has already executed in this run."""
        return step_id in self._executed

    async def run_once(self, step_id: str, fn: Callable[[], Awaitable[Any]]) -> Any:
        """Await ``fn()``, or refuse if ``step_id`` already ran.

        The id is recorded only after ``fn`` returns. A step that raises is
        therefore not marked as executed — but nothing retries it either, so
        this is about honest bookkeeping rather than a retry policy. A real
        retry would need to know whether the failure happened before or after
        the side effect landed, which this cannot tell.

        Note what this does *not* protect against, now that ``fn`` is awaited:
        the check and the recording are separated by a suspension point, so two
        coroutines sharing one tracker could both pass the check before either
        recorded itself. That race cannot arise today because a tracker is
        created per run and never leaves it — the guarantee is single-run
        idempotency, and it rests on that ownership rather than on any locking
        here. Sharing a tracker across concurrent runs would silently void it.

        Raises:
            StepAlreadyExecutedError: ``step_id`` already ran.
        """
        if self.has_run(step_id):
            raise StepAlreadyExecutedError(step_id)
        result = await fn()
        self._executed.add(step_id)
        return result


def _run_meta(
    run_id: str,
    *,
    model: str | None,
    tools_exposed: list[str],
    context: AssembledContext,
    tool_calls_proposed: int,
    tool_calls_dropped: int,
    outcome: str,
) -> TranscriptItem:
    """Build the one item describing how a run was configured.

    Written by both exit paths, so a failed run explains itself as fully as a
    successful one — a run that failed *because* it was pointed at the wrong
    model is precisely the run that needs to say which model it used.

    Deliberately counts rather than copies. Recording the assembled messages and
    the memories verbatim would duplicate the transcript into itself and grow
    quadratically with the conversation, and it would put the system prompt's
    contents in a second place with its own retention question. What a reader
    needs to reconstruct a run is how much it was shown, not another copy.
    """
    return TranscriptItem(
        kind="run_meta",
        payload={
            "model": model,
            "tools_exposed": tools_exposed,
            "messages_in_context": len(context.messages),
            "memories_in_context": context.memories_included,
            "tool_calls_proposed": tool_calls_proposed,
            "tool_calls_dropped": tool_calls_dropped,
            "outcome": outcome,
        },
        run_id=run_id,
    )


@dataclass
class RunResult:
    """The outcome of one completed turn.

    Attributes:
        run_id: Identifies this run. Generated per turn and stamped onto every
            transcript item the turn commits, so it selects the evidence this
            result was produced from — including on the failure path, where the
            exception carries no result but the evidence is committed anyway.
        response: The final model response, after any tool round.
        committed_state: Session state as of the commit. A snapshot, not a live
            view; re-read from the store for anything current.
    """

    run_id: str
    response: ModelResponse
    committed_state: SessionState


class Runtime:
    """Sequences one turn across the model, tool, and state layers.

    Args:
        model_client: Anything satisfying
            :class:`~bacteria.model.protocol.SendsMessages`. The runtime is
            written against the protocol and never against a provider, which is
            what makes providers swappable without touching this file.
        session_store: Anything satisfying
            :class:`~bacteria.session.protocol.SessionRepository`. The runtime
            proposes; only the store writes. Typed as the protocol rather than
            the in-memory class so that a durable store is a second
            implementation and not a change to this file.
    """

    def __init__(self, model_client: SendsMessages, session_store: SessionRepository) -> None:
        self._model_client = model_client
        self._session_store = session_store

    async def run_turn(
        self,
        session_id: str,
        user_text: str,
        tool_registry: ToolRegistry | None = None,
        approve: Approve | None = None,
    ) -> RunResult:
        """Run one turn: assemble, call, optionally use tools, call again, commit.

        Args:
            session_id: Must already exist. The runtime does not create sessions.
            user_text: The incoming message.
            tool_registry: Omit to run without tools — the model is then told of
                none and cannot propose any.
            approve: Gate for each proposed call. Omitting it allows everything,
                which is only appropriate when no registered tool has a side
                effect worth stopping. Interactive callers pass
                :func:`bacteria.tools.approval.cli_approve`.

        Returns:
            The completed run.

        Raises:
            ToolExecutionError: A proposed call was rejected or failed. The turn
                stops; it is not reported back to the model as a soft failure.
                Loud beats graceful here — a model told "that was refused" tends
                to try a variation, which is the opposite of what a refusal
                meant. Evidence of the attempt is committed first.
            UnknownSessionError: No such session.
            ModelLayerError: The model call failed. Evidence is committed first.
        """
        run_id = str(uuid.uuid4())
        step_tracker = StepTracker()

        state = await self._session_store.get_state(session_id)
        context = assemble_context(state, user_text)
        tools = tool_registry.schemas_for_run() if tool_registry else None
        # Names only. The schemas are the model's business; what a run needs
        # recorded is which capabilities were on the table, since a tool that
        # was never offered cannot explain a call that was never made.
        tools_exposed = [schema["name"] for schema in tools or []]

        # Accumulated as the turn progresses rather than assembled at the end,
        # so that a failure part-way still has something to commit. Everything
        # appended here is a proposal until the store applies it.
        #
        # Every item carries `run_id`. That is what separates an abandoned
        # attempt from the retry that followed it: both land in the same
        # session, in order, and without it the two read as one conversation
        # that stuttered.
        evidence = [
            TranscriptItem(
                kind="message", payload={"role": "user", "text": user_text}, run_id=run_id
            )
        ]

        # Accumulated for the `run_meta` record, which both exit paths write.
        # Initialized before the try so that a run failing at the first model
        # call still describes itself — with honest nulls rather than absence.
        answered_by: str | None = None
        tool_calls_proposed = 0
        tool_calls_dropped = 0

        try:
            response: ModelResponse = await step_tracker.run_once(
                f"{run_id}:model_call",
                lambda: self._model_client.send(
                    messages=context.messages, system=context.system, tools=tools
                ),
            )
            answered_by = response.model
            tool_calls_proposed = len(response.tool_calls)

            if response.tool_calls and tool_registry is not None:
                results = await self._execute_tool_calls(
                    run_id=run_id,
                    step_tracker=step_tracker,
                    tool_calls=response.tool_calls,
                    tool_registry=tool_registry,
                    approve=approve if approve is not None else (lambda _tool_call: True),
                    evidence=evidence,
                )
                response = await step_tracker.run_once(
                    f"{run_id}:model_call_after_tools",
                    lambda: self._model_client.send(
                        messages=self._follow_up_messages(context.messages, response, results),
                        system=context.system,
                        tools=tools,
                    ),
                )
                answered_by = response.model
                # Anything this second response asks for is discarded: one round
                # per turn, by ADR 0011. Counted so that the discarding is
                # visible in the record — otherwise the model asking to continue
                # and the model being finished produce identical evidence.
                tool_calls_dropped = len(response.tool_calls)

            evidence.append(
                TranscriptItem(
                    kind="message",
                    payload={"role": "assistant", "text": response.text},
                    run_id=run_id,
                )
            )
            evidence.append(
                _run_meta(
                    run_id,
                    model=answered_by,
                    tools_exposed=tools_exposed,
                    context=context,
                    tool_calls_proposed=tool_calls_proposed,
                    tool_calls_dropped=tool_calls_dropped,
                    outcome="completed",
                )
            )
        except Exception as exc:
            evidence.append(
                TranscriptItem(kind="run_error", payload={"error": str(exc)}, run_id=run_id)
            )
            evidence.append(
                _run_meta(
                    run_id,
                    model=answered_by,
                    tools_exposed=tools_exposed,
                    context=context,
                    tool_calls_proposed=tool_calls_proposed,
                    tool_calls_dropped=tool_calls_dropped,
                    outcome="failed",
                )
            )
            # Deliberately not shielded from cancellation. If the surrounding
            # task is being cancelled this commit may not complete, and that is
            # the honest outcome: a shielded write would let a cancelled turn
            # keep writing to a session whose owner has already gone away.
            await self._session_store.commit(session_id, new_transcript_items=evidence)
            raise

        committed_state = await self._session_store.commit(
            session_id, new_transcript_items=evidence
        )
        return RunResult(run_id=run_id, response=response, committed_state=committed_state)

    async def _execute_tool_calls(
        self,
        run_id: str,
        step_tracker: StepTracker,
        tool_calls: list[ToolCall],
        tool_registry: ToolRegistry,
        approve: Approve,
        evidence: list[TranscriptItem],
    ) -> list[ToolResult]:
        """Run every proposed call in order, recording each outcome.

        Args:
            evidence: Appended to as each call resolves, **including on the
                failure path** — the record of a rejected or failed call is
                written before the exception leaves this method, which is what
                lets the caller commit it. Passing the list in, rather than
                returning items, is what makes that possible.

        Returns:
            One result per call, in proposal order.

        Raises:
            ToolExecutionError: The first call that failed. Remaining calls are
                abandoned; a turn that lost part of its work should not press on
                with the rest of a plan built on it.
        """
        # Sequential, not gathered. Concurrency here would overlap side effects
        # whose ordering the model chose deliberately, and would ask the user to
        # approve several actions at once — both of which trade a guarantee for
        # latency that a turn dominated by model calls will not notice.
        results: list[ToolResult] = []
        for call in tool_calls:
            try:
                result = await step_tracker.run_once(
                    # Keyed by call id so two proposals of the same tool in one
                    # turn are distinct steps rather than a false duplicate.
                    f"{run_id}:tool_call:{call['id']}",
                    # Bound as a default argument: a bare closure over `call`
                    # would capture the loop variable and read its final value.
                    lambda call=call: execute_tool_call(call, tool_registry, approve=approve),
                )
            except ToolExecutionError as exc:
                evidence.append(
                    TranscriptItem(
                        kind="tool_call",
                        payload={
                            "name": call["name"],
                            "input": call["input"],
                            "status": "failed",
                            # Structural, not parsed back out of `error`.
                            # "refused" and "broke" are the same control flow
                            # and different events: one says a boundary held.
                            "reason": exc.reason,
                            "error": str(exc),
                        },
                        run_id=run_id,
                    )
                )
                raise

            results.append(result)
            evidence.append(
                TranscriptItem(
                    kind="tool_call",
                    payload={
                        "name": result.name,
                        "input": call["input"],
                        "status": "executed",
                        "output": result.output,
                    },
                    run_id=run_id,
                )
            )
        return results

    @classmethod
    def _follow_up_messages(
        cls,
        messages: list[dict[str, Any]],
        response: ModelResponse,
        results: list[ToolResult],
    ) -> list[dict[str, Any]]:
        """Build the message list for the post-tool model call.

        Replays the model's own tool request back to it, then supplies the
        results. Both are required: a provider that sees results for a request
        it has no record of making rejects the exchange.
        """
        return messages + [
            {"role": "assistant", "content": cls._assistant_content_blocks(response)},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result.tool_call_id,
                        "content": str(result.output),
                    }
                    for result in results
                ],
            },
        ]

    @staticmethod
    def _assistant_content_blocks(response: ModelResponse) -> list[dict[str, Any]]:
        """Reconstruct the assistant turn from :class:`ModelResponse` fields.

        Built from the normalized fields rather than from ``response.raw``, so
        this works identically whichever provider produced the response —
        reading ``raw`` here would reintroduce exactly the provider coupling the
        protocol exists to remove.

        ``provider_data`` is forwarded verbatim and never inspected. The runtime
        does not know what is in it, does not need to, and must not drop it: for
        some providers it is a required continuation token, and losing it fails
        the follow-up call outright.
        """
        blocks: list[dict[str, Any]] = []
        if response.text:
            blocks.append({"type": "text", "text": response.text})
        blocks.extend(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": call["name"],
                "input": call["input"],
                **({"provider_data": call["provider_data"]} if "provider_data" in call else {}),
            }
            for call in response.tool_calls
        )
        return blocks
