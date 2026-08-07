"""Operator command line: issuing and revoking credentials.

Configuration and wiring only, like every entrypoint. It opens a session, calls
into `fastpaip.auth.service`, and prints the result; the decisions live there.

Exists as a command rather than a route because issuing a key over HTTP needs a
key to authorize it, and the first one has nowhere to come from. Running this
requires access to the machine and the database, which is the correct bar.

Does not create the schema. It used to, which made it a second way for tables to
appear -- and a tool that quietly builds a database when pointed at an empty one
will eventually be pointed at the wrong one and build it there. Run
``just migrate`` first.
"""

import argparse

from fastpaip.auth.service import issue_key, revoke_key
from fastpaip.core.db import get_engine
from fastpaip.core import platform
from sqlmodel.ext.asyncio.session import AsyncSession


async def _issue(principal_id: str, label: str) -> int:
    async with AsyncSession(get_engine()) as session:
        token = await issue_key(session, principal_id=principal_id, label=label)

    print(f"principal: {principal_id}")
    print(f"label:     {label}")
    print(f"key:       {token}")
    print()
    print("Store it now. Only a hash is kept, so this cannot be shown again.")
    return 0


async def _revoke(key_id: str) -> int:
    async with AsyncSession(get_engine()) as session:
        row = await revoke_key(session, key_id=key_id)

    if row is None:
        print(f"no key with id {key_id}")
        return 1
    print(f"revoked {row.key_id} (principal {row.principal_id}) at {row.revoked_at}")
    return 0


def main() -> int:
    """Parse arguments and run the requested command."""
    parser = argparse.ArgumentParser(prog="fastpaip-admin", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    issue = commands.add_parser("issue-key", help="mint an API key for a principal")
    issue.add_argument("principal_id", help="who the key authenticates; owns their sessions")
    issue.add_argument("--label", default="", help="human-readable note, for logs")

    revoke = commands.add_parser("revoke-key", help="make a key unusable")
    revoke.add_argument("key_id", help="the public half of the key, as printed at issue")

    args = parser.parse_args()
    if args.command == "issue-key":
        return platform.run(_issue(args.principal_id, args.label or args.principal_id))
    return platform.run(_revoke(args.key_id))


if __name__ == "__main__":
    raise SystemExit(main())
