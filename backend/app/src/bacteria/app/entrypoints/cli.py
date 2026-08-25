"""Operator command line: credentials, evaluation, a conversation, and its review.

Configuration and wiring only, like every entrypoint. It opens a session, calls
into `bacteria.app.auth.service`, and prints the result; the decisions live there.

Exists as a command rather than a route because issuing a key over HTTP needs a
key to authorize it, and the first one has nowhere to come from. Running this
requires access to the machine and the database, which is the correct bar.

Does not create the schema. It used to, which made it a second way for tables to
appear -- and a tool that quietly builds a database when pointed at an empty one
will eventually be pointed at the wrong one and build it there. Run
``just migrate`` first.
"""

import argparse
import io
import sys
from typing import Mapping, cast

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.store import (
    SESSION_SCOPE,
    USER_SCOPE,
    MemoryScope,
    UnknownSessionError,
)
from bacteria.app.auth import keys
from bacteria.app.auth.service import issue_key, list_keys, principal_is_known, revoke_key
from bacteria.app.chat import review
from bacteria.app.chat.repository import SqlSessionRepository
from bacteria.app.chat.service import run_turn
from bacteria.app.core import observability, platform
from bacteria.app.core.db import get_engine
from bacteria.app.core.jobs import register_tasks
from bacteria.app.core.settings import get_settings, load_env_file
from bacteria.app.evaluation.checks import Policy, evaluate
from bacteria.app.evaluation.runs import load_runs
from bacteria.app.graph.catalogue import PROMOTION_THRESHOLD, promotable
from bacteria.app.graph.repository import tally_relations


async def _issue(principal_id: str, label: str) -> int:
    async with AsyncSession(get_engine()) as session:
        token = await issue_key(session, principal_id=principal_id, label=label)

    # The id is printed as well as the token because `revoke-key` takes the id,
    # and it did not used to appear anywhere in this output -- so the only thing
    # an operator had to copy was the one value revocation rejects. The id is
    # the public half and safe to show, log, and keep.
    parsed = keys.split(token)
    key_id = parsed[0] if parsed else ""

    print(f"principal: {principal_id}")
    print(f"label:     {label}")
    print(f"key id:    {key_id}   (use this to revoke)")
    print(f"key:       {token}")
    print()
    print("Store it now. Only a hash is kept, so this cannot be shown again.")
    return 0


def _plural(count: int, noun: str) -> str:
    """``1 key``, ``2 keys``. Only ever called on nouns that take a plain ``s``."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


async def _list_keys(principal_id: str | None) -> int:
    """Print who holds credentials, so that "check the spelling" has something to check.

    The listing an operator needed and did not have. `chat` refuses an unknown
    principal -- correctly, since `chat_session.user_id` has no foreign key and a
    typo would otherwise create a valid session owned by nobody -- and then told
    them to check a spelling against no available list. Answering that question
    meant opening psql.

    Revoked keys are shown rather than filtered, and marked. An operator reading
    this is usually deciding what to revoke or why something stopped working, and
    "there is no key" and "the key you had was revoked on Tuesday" are different
    answers to that.

    `secret_hash` is on every row and is not printed. Nothing is served by
    putting it on a terminal, and the column exists precisely so that the value
    it stands for is not recoverable from anywhere.
    """
    async with AsyncSession(get_engine()) as session:
        rows = await list_keys(session, principal_id)

    if not rows:
        print("no keys for {}.".format(principal_id) if principal_id else "no keys issued yet.")
        print("`bacteria-admin issue-key <principal>` mints one.")
        return 0

    # Padded to the widest value rather than to a constant, because a principal
    # id is whatever an operator typed and a fixed column truncates the one
    # thing being looked up. The heading is in the max for the same reason it
    # looks pedantic: `acme` is shorter than `principal`, so without it the
    # first listing anyone ran had its columns out of line with its header.
    principal_width = max(max(len(row.principal_id) for row in rows), len("principal"))
    label_width = max(max(len(row.label) for row in rows), len("label"))

    print(
        f"{'principal':<{principal_width}}  {'key id':<16}  issued      {'label':<{label_width}}  status"
    )
    for row in rows:
        status = "active" if row.is_active else f"revoked {row.revoked_at:%Y-%m-%d}"
        print(
            f"{row.principal_id:<{principal_width}}  {row.key_id:<16}  "
            f"{row.created_at:%Y-%m-%d}  {row.label:<{label_width}}  {status}"
        )

    principals = {row.principal_id for row in rows}
    active = sum(1 for row in rows if row.is_active)
    print()
    print(
        f"{_plural(len(rows), 'key')}, {active} active, "
        f"across {_plural(len(principals), 'principal')}."
    )
    return 0


async def _evaluate(
    session_id: str | None, models: list[str], tools: list[str], max_failure_rate: float
) -> int:
    """Judge recorded runs and report, exiting non-zero on any finding.

    Reads the database and writes nothing, so it is safe to point at
    production — which is the case it exists for. The gate drives the same
    checks over seeded fixtures instead; see
    :mod:`bacteria.app.evaluation.fixtures` for why those are not the same claim.
    """
    async with AsyncSession(get_engine()) as session:
        runs = await load_runs(session, session_id=session_id)

    policy = Policy(
        expected_models=frozenset(models),
        approved_tools=frozenset(tools),
        max_failure_rate=max_failure_rate,
    )
    report = evaluate(runs, policy)

    print(f"runs checked: {report.runs_checked}")
    if not runs:
        # Said out loud rather than reported as a pass. Zero runs satisfies
        # every check by having nothing to violate them, and an empty database
        # printing "no findings" is the most misleading output this could give.
        print("no runs found — nothing was judged")
        return 1

    for finding in report.findings:
        where = f" [{finding.run_id}]" if finding.run_id else ""
        print(f"FAIL {finding.check}{where}: {finding.detail}")

    if report.passed:
        print("no findings")
        return 0
    print(f"\n{len(report.findings)} finding(s)")
    return 1


async def _chat(principal_id: str, session_id: str | None) -> int:
    """Hold a conversation against the real database, from a terminal.

    Composition only, like everything here: it opens a session, builds the same
    :class:`~bacteria.app.chat.repository.SqlSessionRepository` the API builds,
    and calls the same :func:`~bacteria.app.chat.service.run_turn`. There is no
    second turn implementation and there must not be — the reply, the
    transcript rows, and the extraction trigger are whatever the HTTP path
    produces, because it is the same function.

    Not the same as ``bacteria-agent``, and the difference is the point. That
    command runs the agent standalone against its in-memory store: a fresh
    session per invocation, nothing persisted, nothing for a job to read
    afterwards. This one writes to Postgres, so conversations survive, resume,
    and can be extracted from.

    Extraction follows ``BACTERIA_MEMORY_EXTRACTION_ENABLED``, exactly as the
    route does. It only *enqueues*, so a worker has to be running for anything
    to come of it — ``just worker``, or ``BACTERIA_RUN_WORKER_IN_API`` on a
    server, neither of which this command is.

    Ownership is not checked when resuming a session. Running this needs the
    database, which is already more access than any ownership rule protects
    against; the equivalent check on the HTTP path exists because a request
    arrives from someone who has only a bearer token.
    """
    settings = get_settings()

    # Procrastinate has to be open before anything can enqueue, and a turn
    # enqueues whenever extraction is on -- without this, the first turn fails
    # with `AppNotOpen` after the model has already answered and the transcript
    # has already been written. The ASGI lifespan does the same thing for the
    # API, and this is the obligation that moving the trigger into `run_turn`
    # put on every entrypoint that runs a turn.
    #
    # Opened unconditionally rather than only when extraction is enabled. The
    # pool costs one connection for the life of an interactive command, and
    # acquiring a resource conditionally on a flag is how a process ends up
    # working in one configuration and failing in the other at the worst moment.
    queue = register_tasks()
    async with queue.open_async(), AsyncSession(get_engine()) as db:
        repository = SqlSessionRepository(db)

        # Before either branch, so it guards resuming as well as creating: the
        # principal reaches `run_turn` and the turn's span either way.
        if not await principal_is_known(db, principal_id):
            print(f"no principal {principal_id}: no key has ever been issued to it.")
            print("check the spelling, or `bacteria-admin issue-key <principal>` first.")
            return 1

        if session_id is None:
            session = await repository.create_session(principal_id)
            session_id = session.session_id
            print(f"new session: {session_id}")
        else:
            # Refuses an id that does not resolve rather than creating one: a
            # wrong session id usually means it was copied wrong, and silently
            # opening an empty conversation instead would look like the
            # transcript had been lost. Reported rather than raised, because a
            # traceback for a mistyped argument tells an operator nothing they
            # did not already know.
            try:
                await repository.get_state(session_id)
            except UnknownSessionError:
                print(f"no session {session_id}")
                return 1
            print(f"resuming: {session_id}")

        print(f"provider: {settings.model_provider}", end="")
        if settings.memory_extraction_enabled:
            # The worker is named in the output rather than only in the
            # docstring because this command is the one most likely to be run
            # *in order to* see what extraction produces, and it enqueues
            # without performing. Turning it on and seeing no proposals is the
            # expected result of forgetting `just worker`, and nothing else
            # here would say so.
            print("  extraction: on (needs a running worker: `just worker`)")
        else:
            print("  extraction: off")
        print("(empty line or Ctrl+C to quit)")

        # Printed when it changes rather than every turn. A count repeated
        # before every prompt is noise, and a nudge people scroll past is the
        # thing this is trying to prevent rather than an acceptable version of
        # it. `None` so the first prompt reports even when nothing is waiting is
        # false -- zero is not worth announcing.
        announced: int | None = None

        while True:
            waiting = await repository.count_proposals(session_id)
            if waiting and waiting != announced:
                # The gap the README lists: proposals accumulate, nothing says
                # so, and the feature looks broken while behaving exactly as
                # designed. The count lags by a turn because extraction is
                # deferred -- what shows before turn N is what the worker
                # finished from turn N-1 -- which is why this sits above the
                # prompt rather than under the reply, where it would read as
                # that turn's result.
                # Points at `/review` rather than the one-shot command it used
                # to name: the decision can now be made without leaving the
                # conversation, and a nudge that sends someone to another
                # terminal is one they postpone.
                print(f"[{waiting} waiting: /review]")
            announced = waiting

            # Ends the read transaction the count above opened, before this
            # process spends minutes doing nothing.
            #
            # **This blocked a migration.** `ALTER TABLE chat_memory_proposal ADD
            # COLUMN` waited behind a session sitting `idle in transaction` at
            # this prompt, holding a lock taken by `count_proposals`. Nothing
            # errored: Postgres queued the DDL, and everything queued behind that
            # in turn. On a deployment whose migration step runs before the
            # process starts, that is a deploy that hangs with no message.
            #
            # A rollback rather than a commit because nothing here wrote
            # anything, and a rollback that discards nothing says so. Placed
            # before `input` rather than after the count, so any read added to
            # this loop later is covered by where it sits rather than by whoever
            # remembers.
            await db.rollback()

            try:
                # Blocking `input` on the event loop, knowingly, and for the
                # same reason the agent's own CLI does it: this process runs one
                # turn at a time and has nothing else to schedule. A surface
                # serving more than one caller must not read its input this way.
                user_text = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_text:
                break

            command = review.parse_console_line(user_text)
            if not isinstance(command, review.SendMessage):
                await _run_console_command(repository, session_id, command)
                # Back to the top, which re-counts: accepting one of three
                # proposals then reports two, so the effect of the command is
                # visible without asking for it again.
                continue
            # Whatever `review` decided should actually be sent -- the `//`
            # escape means that is not always what was typed.
            user_text = command.text

            result = await run_turn(
                repository=repository,
                provider=settings.model_provider,
                session_id=session_id,
                user_text=user_text,
                principal=principal_id,
                extract=settings.memory_extraction_enabled,
                build_graph=settings.graph_extraction_enabled,
            )
            print(result.response.text)

    return 0


def _print_entry(
    entry: review.PendingEntry, activated: Mapping[str, review.Held] | None = None
) -> None:
    """The body of one proposal, shared by the listing and the walk.

    Shared so the two cannot come to describe the same proposal differently --
    in particular the `note:` line, which is the one piece of a listing that
    changes what a reasonable person decides.

    ``activated`` is what the caller has accepted since the listing was taken. A
    one-shot listing has nothing to pass; a walk does, and without it the note
    goes stale exactly when it matters -- on the second proposal for a key whose
    first was accepted a moment earlier.
    """
    print(f"  value:  {entry.value}")
    print(f"  reason: {entry.reason}")
    # One line per scope, naming the scope's own keystroke. The single line this
    # replaced joined the scopes with "and" -- which read as though accepting
    # replaced both, when a keystroke chooses one and leaves the other standing.
    for held in review.held_now(entry, activated or {}):
        print(f"  note:   accepting at {held.scope} replaces: {held.value}")


def _print_pending(result: review.Pending | review.NoSuchSession) -> int:
    """Render a listing. The decisions it renders were made in `chat.review`."""
    if isinstance(result, review.NoSuchSession):
        print(f"no session {result.session_id}")
        return 1

    if not result.entries:
        print("no proposals waiting")
        return 0

    for entry in result.entries:
        print(f"{entry.source}/{entry.key}")
        _print_entry(entry)

    print()
    print(f"{len(result)} waiting. Accept or reject one by source and key.")
    return 0


async def _list_proposals(repository: SqlSessionRepository, session_id: str) -> int:
    return _print_pending(await review.pending(repository, session_id))


_REVIEW_KEYS = "  ".join(f"[{key}] {label}" for key, (label, _) in review.REVIEW_CHOICES.items())
"""The legend, built from the table that also does the parsing.

Written out by hand it would be a second list of keys, free to disagree with the
one that decides what they do -- which is the failure `_SLASH_HELP` is still
exposed to and this is not.
"""


def _ask_review_key() -> review.ReviewDecision:
    """Read one decision, asking again until the answer means something.

    EOF and interrupt end the walk and nothing else. The outer loop reads them as
    "quit", which is right at a conversation prompt and wrong here: someone
    pressing Ctrl+C to get out of a review they opened by mistake should not also
    lose the session they were in the middle of.
    """
    while True:
        try:
            answer = input("> ")
        except (EOFError, KeyboardInterrupt):
            # The interrupt leaves the cursor mid-line; without this the summary
            # prints onto the prompt.
            print()
            return review.StopReview()

        decision = review.parse_review_key(answer)
        if not isinstance(decision, review.Unclear):
            return decision
        print(_REVIEW_KEYS)


async def _review_each(repository: SqlSessionRepository, session_id: str) -> int:
    """Walk the queue, deciding one proposal at a time.

    Exists because a listing is not a workflow. `/proposals` prints a source and
    a key for each entry so they can be typed back onto `/accept` -- six copied
    identifiers to clear three proposals -- and it shows `held_by`, the thing
    accepting would replace, one decision before the decision it bears on. This
    shows one, asks, and applies the answer where it was given.

    Re-reads nothing as it goes. The listing is taken once and walked, which is
    correct here because this process is the only writer and runs one turn at a
    time; a surface with concurrent reviewers would have to re-check each entry
    before applying a decision to it.
    """
    result = await review.pending(repository, session_id)
    if isinstance(result, review.NoSuchSession):
        print(f"no session {result.session_id}")
        return 1
    if not result.entries:
        print("no proposals waiting")
        return 0

    total = len(result)
    accepted = 0
    rejected = 0
    stopped = False

    # What this walk has activated, so the `note:` line reflects the reviewer's
    # own answers rather than the listing taken before they gave any.
    activated: dict[str, review.Held] = {}

    for position, entry in enumerate(result.entries, start=1):
        print(f"{position}/{total}  {entry.source}/{entry.key}")
        _print_entry(entry, activated)
        print(_REVIEW_KEYS)

        decision = _ask_review_key()
        if isinstance(decision, review.StopReview):
            stopped = True
            break
        if isinstance(decision, review.AcceptThis):
            # Recorded only when the write succeeded. A failed accept that still
            # updated `activated` would make every later note name a value that
            # was never stored -- the stale note this tracking exists to prevent,
            # reintroduced from the other direction.
            if await _accept_proposal(
                repository, session_id, entry.source, entry.key, decision.scope
            ):
                continue
            activated[entry.key] = review.Held(decision.scope, entry.value)
            accepted += 1
        elif isinstance(decision, review.RejectThis):
            await _reject_proposal(repository, session_id, entry.source, entry.key)
            rejected += 1

    # Always, including when nothing was decided. Someone who skipped every
    # proposal and someone who stopped at the first are in different situations,
    # and both need to know the queue is still there.
    waiting = total - accepted - rejected
    summary = f"{accepted} accepted, {rejected} rejected, {waiting} still waiting"
    print(f"stopped -- {summary}" if stopped else summary)
    return 0


async def _accept_proposal(
    repository: SqlSessionRepository, session_id: str, source: str, key: str, scope: str
) -> int:
    result = await review.accept(repository, session_id, source, key, cast(MemoryScope, scope))
    if isinstance(result, review.NoSuchSession):
        print(f"no session {result.session_id}")
        return 1
    if isinstance(result, review.NoSuchProposal):
        print(f"no proposal {result.source}/{result.key} in that session")
        return 1

    print(f"activated {result.key!r} at {result.scope} scope: {result.entry.value}")
    return 0


async def _reject_proposal(
    repository: SqlSessionRepository, session_id: str, source: str, key: str
) -> int:
    result = await review.discard(repository, session_id, source, key)
    if isinstance(result, review.NoSuchSession):
        print(f"no session {result.session_id}")
        return 1

    if result.present:
        print(f"discarded {result.source}/{result.key}")
    else:
        print(f"nothing to discard: no {result.source}/{result.key}")
    return 0


_SLASH_HELP = """  /review                       decide on each one in turn
  /proposals                    what is waiting for a decision
  /accept <source> <key> [user] make one active; `user` carries it to later sessions
  /reject <source> <key>        discard one
  /help                         this
Anything else is sent to the model. Begin a message with // to send a literal /.
"""


async def _run_console_command(
    repository: SqlSessionRepository, session_id: str, command: review.ConsoleCommand
) -> None:
    """Print the result of one command `chat.review` already parsed.

    A mapping from outcome to output, which is what an entrypoint is for. What
    the words mean, which arguments are valid, and whether an unrecognized line
    reaches the model are decided in `chat.review` -- where they are tested,
    because this file is omitted from coverage on the grounds that it holds no
    decisions.
    """
    if isinstance(command, review.ListPending):
        await _list_proposals(repository, session_id)
    elif isinstance(command, review.ReviewEach):
        await _review_each(repository, session_id)
    elif isinstance(command, review.AcceptOne):
        await _accept_proposal(repository, session_id, command.source, command.key, command.scope)
    elif isinstance(command, review.DiscardOne):
        await _reject_proposal(repository, session_id, command.source, command.key)
    elif isinstance(command, review.ShowHelp):
        if command.detail:
            print(command.detail)
        print(_SLASH_HELP, end="")


async def _one_shot(handler, *args) -> int:
    """Open a session for a single review command run from the shell.

    The conversation loop already owns one, so the review functions take a
    repository rather than making one. This is the other caller: it exists so
    that ``bacteria-admin list-proposals`` and ``/proposals`` are the same code
    reached two ways, rather than two implementations that drift the first time
    one of them learns something.
    """
    async with AsyncSession(get_engine()) as db:
        return await handler(SqlSessionRepository(db), *args)


async def _relations(threshold: int) -> int:
    """Report relation names the extractor keeps producing and the catalogue lacks.

    **A command rather than the periodic job ADR 0007 sketched**, and the reason
    is in that record's own "not built": nothing acts on the count, and promotion
    is an edit to a literal that a person makes. A scheduled job would write the
    same list into a log nobody tails; asking is a thing someone *does*, so it is
    a thing they run. When something ever acts on it, the query is already here
    and the schedule is a wrapper.

    Reports and never promotes. A relation appearing three times is a reason to
    look, and the rule of three says nothing about whether a regularity is an
    invariant — a wrongly admitted relation generates false contradictions
    forever, which is worse than having none.
    """
    async with AsyncSession(get_engine()) as db:
        candidates = promotable(await tally_relations(db), threshold=threshold)

    if not candidates:
        print(f"No relation outside the catalogue has been seen {threshold} times.")
        return 0

    print(f"Seen {threshold}+ times and not in the catalogue:")
    for candidate in candidates:
        print(f"  {candidate.count:>4}  {candidate.name}")
    print("\nPromote one by adding it to CATALOGUE in bacteria/app/graph/catalogue.py.")
    return 0


async def _revoke(key_id: str) -> int:
    if keys.split(key_id) is not None:
        # A whole key was passed where an id belongs. Refused rather than
        # accepted, even though the id is trivially recoverable from it: this
        # command is most often run *because* a key leaked, and quietly taking
        # the full token would put the secret in shell history at exactly that
        # moment. The token is not echoed back here for the same reason.
        print("that is a full key, not a key id.")
        print("pass the middle segment -- `fp_<key id>_<secret>` -- shown as 'key id' at issue.")
        return 1

    async with AsyncSession(get_engine()) as session:
        row = await revoke_key(session, key_id=key_id)

    if row is None:
        print(f"no key with id {key_id}")
        return 1
    print(f"revoked {row.key_id} (principal {row.principal_id}) at {row.revoked_at}")
    return 0


def main() -> int:
    """Parse arguments and run the requested command."""
    # Before anything prints. This command relays arbitrary model output --
    # replies, proposed values -- and on Windows stdout defaults to the ANSI
    # code page, cp1252 here. Anything outside it (an emoji, CJK, a curly quote)
    # raises UnicodeEncodeError, which kills a conversation mid-turn *after* the
    # model has been paid for. `errors="replace"` degrades one character to `?`
    # instead, which is the right trade for an interactive command: a mangled
    # glyph is a nuisance, a crashed session is lost work.
    #
    # Guarded because a replaced stdout -- a test harness, a pipe wrapper -- need
    # not be a TextIOWrapper, and this is configuration rather than something
    # worth failing startup over. `isinstance` rather than `hasattr`: the latter
    # narrows to `object` for a type checker, so the call reads as calling
    # something uncallable and needs a suppression to say otherwise.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_env_file()
    # The third entrypoint, and it gets the same treatment as the other two for
    # the reason `run_turn`'s `extract` argument gives about entrances: this one
    # holds real conversations, so a deployment where two processes are traced
    # and the third is not is a gap nothing announces. `chat` is also the only
    # surface that reaches the model without HTTP, which makes it the one place
    # a provider's spans can be seen on their own.
    #
    # Silently, though. Instrumented with the console on, this printed nine query
    # spans between a typed question and the model's answer -- telemetry in the
    # one stream that exists to relay what a model said.
    observability.configure(service_name="bacteria-admin", console=False)

    parser = argparse.ArgumentParser(prog="bacteria-admin", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    issue = commands.add_parser("issue-key", help="mint an API key for a principal")
    issue.add_argument("principal_id", help="who the key authenticates; owns their sessions")
    issue.add_argument("--label", default="", help="human-readable note, for logs")

    revoke = commands.add_parser("revoke-key", help="make a key unusable")
    revoke.add_argument(
        "key_id",
        help="the key id shown at issue -- the middle segment of fp_<key id>_<secret>, not the whole key",
    )

    chat = commands.add_parser("chat", help="hold a conversation against the real database")
    chat.add_argument(
        "principal_id",
        help="who owns the session; the same identifier a key authenticates as",
    )
    chat.add_argument(
        "--session",
        default=None,
        help="resume this session id instead of opening a new one",
    )

    keys_listing = commands.add_parser("list-keys", help="show who holds credentials")
    keys_listing.add_argument(
        "--principal",
        default=None,
        help="restrict to one principal; omit to list every key ever issued",
    )

    listing = commands.add_parser("list-proposals", help="show memories awaiting a decision")
    listing.add_argument("session_id", help="the conversation whose proposals to review")

    accept = commands.add_parser("accept-proposal", help="make a suggested memory active")
    accept.add_argument("session_id")
    accept.add_argument("source", help="who proposed it; half of a proposal's identity")
    accept.add_argument("key", help="the other half -- two sources may suggest the same key")
    accept.add_argument(
        "--scope",
        choices=[SESSION_SCOPE, USER_SCOPE],
        default=SESSION_SCOPE,
        help="`user` carries the fact into every later conversation; defaults to this session",
    )

    reject = commands.add_parser("reject-proposal", help="discard a suggested memory")
    reject.add_argument("session_id")
    reject.add_argument("source")
    reject.add_argument("key")

    evaluate_cmd = commands.add_parser("eval", help="judge recorded runs against a policy")
    evaluate_cmd.add_argument(
        "--session", default=None, help="restrict to one session; omit to judge every run"
    )
    evaluate_cmd.add_argument(
        "--model",
        action="append",
        default=[],
        help="a model runs are allowed to have used; repeatable. Omitted, the check is skipped",
    )
    evaluate_cmd.add_argument(
        "--tool",
        action="append",
        default=[],
        help="a tool runs are allowed to have been offered; repeatable",
    )
    evaluate_cmd.add_argument(
        "--max-failure-rate",
        type=float,
        default=1.0,
        help="proportion of runs allowed to have failed, 0 to 1",
    )

    relations_cmd = commands.add_parser(
        "relations", help="show relation names the catalogue does not cover"
    )
    relations_cmd.add_argument(
        "--threshold",
        type=int,
        default=PROMOTION_THRESHOLD,
        help="how many times a name must appear to be listed; the rule of three by default",
    )

    args = parser.parse_args()
    if args.command == "relations":
        return platform.run(_relations(args.threshold))
    if args.command == "issue-key":
        return platform.run(_issue(args.principal_id, args.label or args.principal_id))
    if args.command == "chat":
        return platform.run(_chat(args.principal_id, args.session))
    if args.command == "list-keys":
        return platform.run(_list_keys(args.principal))
    if args.command == "list-proposals":
        return platform.run(_one_shot(_list_proposals, args.session_id))
    if args.command == "accept-proposal":
        return platform.run(
            _one_shot(_accept_proposal, args.session_id, args.source, args.key, args.scope)
        )
    if args.command == "reject-proposal":
        return platform.run(_one_shot(_reject_proposal, args.session_id, args.source, args.key))
    if args.command == "eval":
        return platform.run(_evaluate(args.session, args.model, args.tool, args.max_failure_rate))
    return platform.run(_revoke(args.key_id))


if __name__ == "__main__":
    raise SystemExit(main())
