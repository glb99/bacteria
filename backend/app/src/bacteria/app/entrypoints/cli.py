"""Operator command line: credentials, evaluation, and a conversation.

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

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth import keys
from bacteria.app.auth.service import issue_key, revoke_key
from bacteria.app.chat.repository import SqlSessionRepository
from bacteria.app.chat.service import run_turn
from bacteria.app.core import platform
from bacteria.app.core.db import get_engine
from bacteria.app.core.settings import get_settings, load_env_file
from bacteria.app.evaluation.checks import Policy, evaluate
from bacteria.app.evaluation.runs import load_runs


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

    async with AsyncSession(get_engine()) as db:
        repository = SqlSessionRepository(db)

        if session_id is None:
            session = await repository.create_session(principal_id)
            session_id = session.session_id
            print(f"new session: {session_id}")
        else:
            # Fails loudly on an id that does not resolve, rather than creating
            # one: a session id that is wrong usually means it was copied
            # wrong, and silently opening an empty conversation instead would
            # look like the transcript had been lost.
            await repository.get_state(session_id)
            print(f"resuming: {session_id}")

        print(f"provider: {settings.model_provider}", end="")
        print("  extraction: on" if settings.memory_extraction_enabled else "  extraction: off")
        print("(empty line or Ctrl+C to quit)")

        while True:
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

            result = await run_turn(
                repository=repository,
                provider=settings.model_provider,
                session_id=session_id,
                user_text=user_text,
                extract=settings.memory_extraction_enabled,
            )
            print(result.response.text)

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
    load_env_file()

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

    args = parser.parse_args()
    if args.command == "issue-key":
        return platform.run(_issue(args.principal_id, args.label or args.principal_id))
    if args.command == "chat":
        return platform.run(_chat(args.principal_id, args.session))
    if args.command == "eval":
        return platform.run(_evaluate(args.session, args.model, args.tool, args.max_failure_rate))
    return platform.run(_revoke(args.key_id))


if __name__ == "__main__":
    raise SystemExit(main())
