"""Asking the world how a codebase is doing, and refusing to remember the answer.

Everything else in this feature reads files. This runs something, which makes it
the first **world-action** here and puts it on the other side of a line
[ADR 0004's sibling reasoning] and §7 of the design draw deliberately: a
model-action changes what we believe, a world-action changes or inspects the
world. Palantir merges them eventually. This does not yet, and the surface
badges them apart, because a view that does both makes the distinction invisible
at the moment it starts to matter.

**A reading is not a belief, and is never written to the log.** The tests were
green four minutes ago and may be red now; the log holds claims that were true
when somebody said them, and a fact with a shelf life of one commit would make
every replay of a past run wrong in a new way. So a reading is returned, shown,
and forgotten. It clears itself by being re-taken.

**Nothing is ever run from a request.** The command belongs to the project and
is set when the project is configured; a caller says *take the reading*, never
*run this*. That is the whole security posture of this module and it is one
sentence on purpose: a route that accepted a command would be remote code
execution with extra steps, whatever the intent of the person adding it.
"""

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from bacteria.app.architecture.models import Project

State = Literal["ok", "failing", "unavailable"]

TIMEOUT_SECONDS = 600
"""Long enough for a real suite, short enough that a hung run ends.

A test suite is the slowest honest thing this will ever wait for. Without a
bound a wedged process holds a request until something else times out, and the
answer a person gets is about the proxy rather than about their code.
"""

OUTPUT_LIMIT = 8000
"""How much of the tail is kept.

The tail rather than the head: a failing suite says what failed at the end, and
the first eight thousand characters of pytest are the collection log.
"""


@dataclass(frozen=True)
class Reading:
    """What the world said when we asked, and when.

    Deliberately not an :class:`~bacteria.app.graph.log.Assertion`. It carries no
    validity interval and no author because nobody said it -- a process exited
    with a status, which is a different kind of thing from a claim, and giving it
    the shape of one would invite it into a log it must not enter.
    """

    probe: str
    state: State
    detail: str
    output: str
    at: datetime

    @property
    def ok(self) -> bool:
        return self.state == "ok"


async def run_tests(project: Project) -> Reading:
    """Run the project's own test command and report what happened.

    ``unavailable`` is a third state and not a failure. A project with no command
    configured has not told us how to check it, which is different from having
    checked and found something wrong -- and a surface that drew them the same
    way would report a green tick for a suite nobody ran, which is the failure
    this whole feature is arguing against.
    """
    now = datetime.now(timezone.utc)
    if not project.test_command:
        return Reading(
            probe="tests",
            state="unavailable",
            detail="no test command configured for this project",
            output="",
            at=now,
        )

    location = Path(project.location)
    if not location.is_dir():
        return Reading(
            probe="tests",
            state="unavailable",
            detail=f"cannot reach {project.location}",
            output="",
            at=now,
        )

    try:
        # A thread and a blocking call, not `asyncio.create_subprocess_shell`,
        # and the reason is specific to this application. `core/platform.py`
        # runs it on `SelectorEventLoop` on Windows *on purpose*, because
        # psycopg's async mode refuses to run on the Proactor loop -- and the
        # selector loop has no subprocess support at all. The async spelling
        # raises `NotImplementedError` from deep inside asyncio, in production
        # as well as under test, on the platform this is developed on.
        #
        # `to_thread` sidesteps the loop entirely: the work blocks a worker
        # thread rather than the event loop, and it behaves the same everywhere.
        completed = await asyncio.to_thread(
            subprocess.run,
            project.test_command,
            cwd=str(location),
            shell=True,
            stdout=subprocess.PIPE,
            # Merged into stdout rather than captured beside it, so the two
            # arrive interleaved in the order they were written. A suite that
            # prints progress to one and a traceback to the other is unreadable
            # once they are concatenated after the fact.
            stderr=subprocess.STDOUT,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return Reading(
            probe="tests",
            state="unavailable",
            detail=f"still running after {TIMEOUT_SECONDS}s, killed",
            output="",
            at=datetime.now(timezone.utc),
        )
    except OSError as error:
        return Reading(
            probe="tests",
            state="unavailable",
            detail=f"could not start it: {error}",
            output="",
            at=now,
        )

    raw = completed.stdout
    text = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw or "")
    output = text[-OUTPUT_LIMIT:]
    passed = completed.returncode == 0
    return Reading(
        probe="tests",
        state="ok" if passed else "failing",
        detail=("the suite passed" if passed else f"the suite exited {completed.returncode}"),
        output=output,
        at=datetime.now(timezone.utc),
    )


def describe(reading: Optional[Reading]) -> str:
    """One line for a reading, or for never having taken one.

    ``None`` is its own sentence rather than an empty string, because *not
    checked* has to be legible as a state. Everything on this surface has the
    same rule and this is the place it is easiest to break.
    """
    if reading is None:
        return "not checked"
    return f"{reading.state} — {reading.detail}"
