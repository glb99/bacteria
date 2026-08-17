"""Background worker entrypoint: configuration, and nothing else.

Runs jobs enqueued by anything else in the system. It defines no work of its
own — the tasks live with the features that own them, and this process only
decides which queues to serve and with what concurrency.

Run it alongside the web server:

    uv run bacteria-worker

A worker and the API are separate processes on purpose. They fail differently,
scale differently, and a slow import must not be able to make the API
unresponsive — which is precisely what happens while ingestion runs inline.

One deployment shape does not get that, and it is worth knowing here rather than
discovering it from the other side. A platform that runs a single ASGI process
has nowhere to put this command, and with no worker anywhere
``POST /ingestion/batches:defer`` answers ``202`` for work nothing performs. So
``BACTERIA_RUN_WORKER_IN_API`` starts a worker from the API's lifespan instead,
off by default, and every consequence above is genuinely surrendered when it is
on. See [ADR 0001](../../../../../docs/adr/0001-run-the-worker-in-the-api-process.md).

Do not set it anywhere this command can run. Two workers on one queue is not an
error either of them can detect.
"""

import argparse
import logging

from bacteria.app.core import observability, platform
from bacteria.app.core.jobs import register_tasks
from bacteria.app.core.settings import get_settings, load_env_file


async def _run(queues: list[str] | None, concurrency: int) -> None:
    app = register_tasks()
    async with app.open_async():
        # `queues=None` is procrastinate's documented "listen to every queue",
        # which its own annotation (`Iterable[str]`) does not admit.
        await app.run_worker_async(queues=queues, concurrency=concurrency)  # ty: ignore[invalid-argument-type]


def main() -> int:
    """Parse arguments and run the worker until interrupted."""
    # Every entrypoint loads it, including the ones with no provider key to find
    # today. The bug being fixed was one process behaving differently from
    # another for reasons invisible in the code, and "which of the three reads
    # `.env`" is the same question in a smaller form.
    load_env_file()

    parser = argparse.ArgumentParser(prog="bacteria-worker", description=__doc__)
    parser.add_argument(
        "--queue",
        action="append",
        dest="queues",
        help="serve only this queue; repeatable. Omit to serve all of them.",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    logging.basicConfig(level=get_settings().log_level)
    # A different service name from the API's, which is the point: ADR 0001's
    # open question is whether a job and a request contended, and that is only
    # askable once the two are labelled apart on one timeline. A deployment
    # running the worker in-process reports `bacteria-api` for both, and the job
    # spans are still distinguishable by name -- which is the shape of the
    # answer there.
    observability.configure(service_name="bacteria-worker")
    try:
        platform.run(_run(args.queues, args.concurrency))
    except KeyboardInterrupt:
        # An interrupted worker is an ordinary way to stop one, not a crash.
        # Procrastinate finishes the job in hand before the loop exits.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
