---
date: 2026-10-28
status: gaps
question: "Can app.cli.cli be run by bgt.SupervisedService?"
adr: ""
---

# Can app.cli.cli be run by bgt.SupervisedService?

## Why this session

The person asked whether `app.cli.cli` can be run by `bgt.SupervisedService`. They believe the runtime can run wrapped in a supervised job by using bgt. Asked which decision that understanding would change, they answered "that noy". This session reads that as no decision to change. They then asked whether it could run interactively as a `SupervisedService`, whether that is difficult to implement, and then said "implement it".

## Starting model

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "that I can run the runtime wrapped in a supervised job by using bgt" |
| Which decision would this understanding change? | "that noy" |

## Evidence

- `backend/app/src/app/cli/cli.py` `main` calls `bgt.SupervisedService.start(bgt.as_work_factory(_run), name="bacteria-run", wakeup=bgt.IntervalOnlyWakeup(), interval=2)` and then returns. The following line, `anyio.run(_run)`, is commented out. The docstring of `main` says the event loop is started there, at the outermost edge.
- `backend/app/src/app/cli/cli.py` `_run` is `async def`. It loads the environment, creates one in-memory session, and loops on `input` until an empty line, EOF, or interrupt. Each non-empty line awaits `run_turn`. The docstring says exceptions from a turn are not caught.
- `backend/app/src/app/bgt/typing.py` `DoWork.__call__` returns `bool`: `True` to run again immediately, or `False` to wait for the next wakeup. The same file says a work callable must do one bounded work unit. `as_work_factory` wraps that callable in a factory with no setup or cleanup.
- `backend/app/src/app/bgt/_service.py` `Service._run_once` sets `again = do_work()` and repeats while `again` is true and the stop event is clear. `IntervalOnlyWakeup` starts woken, so the first work unit is attempted at startup. `SupervisedService.start` builds that service and starts a `Supervisor`.
- `backend/app/src/app/bgt/_supervisor.py` `Supervisor.start` runs `_supervise` on a thread named `supervisor-{name}` with `daemon=True`. `_supervise` calls `loop.run`. An exception from the loop is logged as `supervisor.loop_crashed`, then the loop is started again after a backoff. A clean return ends supervision.
- The CLI imports that in-tree package: `from app import bgt`, and `backend/app/src/app/bgt/` is the package that defines `SupervisedService`. `backend/app/pyproject.toml` also depends on the distribution `bgt>=26.2.0`.
- A probe on 2026-10-28 kept the process alive and passed an `async def job` through `app.bgt.as_work_factory` to `SupervisedService.start`. In 0.15 seconds the coroutine body recorded no entry, and Python emitted 45024 warnings, the first of which was `RuntimeWarning: coroutine 'job' was never awaited`. The supervisor thread was `supervisor-probe-async` and `daemon` was `True`. `stop(timeout=1)` then returned `True`.
- A second probe on 2026-10-28 started `SupervisedService` and returned from the main thread. The child printed `supervisor.started` and `MAIN_RETURN 0.001`. It did not print the work unit's `JOB` line. The process then aborted during interpreter shutdown. Stderr began `Fatal Python error: _enter_buffered_busy: could not acquire lock for <_io.BufferedWriter name='<stdout>'> at interpreter shutdown, possibly due to daemon threads`. The exit code was `3221226505`.
- `Service.run` enters the work factory once for the loop run, then calls that same `do_work` on every unit. `has_completed_cycle` is set `True` only after `do_work()` returns. Source: `backend/app/src/app/bgt/_service.py`.
- `SupervisedService` exposes `is_running` and `stop`. It has no call that waits until the work itself finishes. Source: `backend/app/src/app/bgt/_service.py`.
- A third probe on 2026-10-28 passed a synchronous callable that ran an async body with `anyio.run`. The body recorded the thread name `supervisor-probe-wrap`.
- The same probe used a callable that returned `False` and an interval of 0.2 seconds. In 0.75 seconds the callable ran 4 times.
- The same probe blocked a callable on an event. `stop(timeout=0.4)` returned `False` after 0.407 seconds while `is_running` stayed `True`. After the event was set, `stop(timeout=1)` returned `True` and `is_running` was `False`.
- The same probe raised `RuntimeError` from the first call. The log contained `supervisor.loop_crashed` and `supervisor.restarting` with `backoff=0.108937113804288`. The callable then ran a second time. `has_completed_cycle` was `False` in the crash traceback.
- The aligned session [2026-10-27-agent-run-retry-on-collapse.md](2026-10-27-agent-run-retry-on-collapse.md) says a collapsed run is `run_turn` raising, that the CLI does not start that run again, and that the person chose two further attempts with the finished tool step kept. `backend/app/src/app/cli/__init__.py` says an interface that decides when to retry has become a second runtime.
- `Supervisor.stop` sets the stop event, wakes the loop, then `join`s the supervisor thread. Source: `backend/app/src/app/bgt/_supervisor.py`.
- `main`'s docstring says the event loop is started there, at the outermost edge, and nowhere else, so the runtime can be embedded in a process that already has a loop. Source: `backend/app/src/app/cli/cli.py`.
- A probe on 2026-10-28 called `SupervisedService.stop(timeout=0.3)` from inside the work unit on `supervisor-probe-self-stop`. `Thread.join` raised `RuntimeError: cannot join current thread`. The supervisor logged `supervisor.loop_crashed_during_shutdown` and `supervisor.stopped`. The line after `stop` in the work unit did not run. After that, `is_running` was `False`.

## Inferences

- Passing `_run` to `as_work_factory` does not enter the runtime. `_run` is async, so the call in `Service._run_once` returns a coroutine. A coroutine is truthy, so `again` stays true and `_run_once` calls it again immediately. The probe showed that loop: the body never ran, and the warnings were `coroutine was never awaited`. This rests on `cli.py`, `typing.py`, `_service.py`, and the first probe.
- `main` returning does not leave that supervisor running the CLI. The supervisor thread is a daemon, and `main` does not wait on it. The second probe returned from the main thread 0.001 seconds after start, never entered the work unit, and aborted during shutdown. This rests on `cli.py`, `_supervisor.py`, and the second probe.
- A crash restart from this supervisor applies to a work unit that raises out of `loop.run`. The current `_run` call does not reach `run_turn`, so a turn failure is not what this `main` restarts. This rests on `_supervisor.py` and the CLI loop docstring.
- The interactive session can be the body of a work unit when a synchronous callable drives it and the main thread stays blocked. `anyio.run` around an async body runs on `supervisor-<name>`. This rests on the third probe and on `daemon=True` in `_supervisor.py`.
- A normal return from that unit waits for the interval and calls the unit again. With `_run` as that unit, each call constructs a new in-memory session, so the prompt comes back as a new session. `main` sets the interval to 2 seconds. This rests on `_service.py`, the four calls in 0.75 seconds, and the session constructed at the start of `_run`.
- A raise from that unit ends the loop run. The supervisor starts another loop run after backoff, and that run calls the unit again. The third probe showed one `RuntimeError` followed by a second call. Inside one call to `_run`, `has_completed_cycle` stays `False` until that call returns, so a raise from the session is a loop run that has not completed a cycle. This rests on the assignment after `do_work()` in `_service.py` and on the crash traceback.
- `stop` joins the supervisor thread. While the unit is blocked, the join waits out its timeout and the thread stays alive. The blocked-unit probe showed `stop(timeout=0.4)` returning `False` with `is_running` still `True`. An interactive `input` is that kind of block. This rests on `_run_once` checking the stop event after `do_work()` returns, and on that probe.
- A supervisor restart of `_run` is a new session and a new `run_turn` for the next line. It is a different mechanism from the collapsed-run retry in the 2026-10-27 session, which is two further attempts of the run that raised, with the finished tool step kept. This rests on `_run` creating the session inside the call, and on that session's shared model.
- The code that places the prompt on the supervisor thread is a synchronous wrapper around `anyio.run(_run)` plus a blocked main thread. The lifetime is the larger part. `stop` joins the supervisor thread, so a call from the work unit raises `RuntimeError: cannot join current thread` and ends supervision through `supervisor.loop_crashed_during_shutdown`. The clean quit is a signal from the work unit and `stop` on the main thread, issued before the interval starts another session. This rests on `Supervisor.stop`, the self-stop probe, and the four repeats after a `False` return.
- Catching a turn exception inside the wrapper keeps the supervisor from starting a new session. That catch is local to the wrapper. The collapsed-run retry, two further attempts with the finished tool step kept, is still the open work from the 2026-10-27 session. This rests on that session and on `_supervisor.py`.
- `anyio.run(_run)` now runs inside `_session_work`, on the supervisor thread. `main` waits for a clean return and then calls `stop` from the main thread. This rests on `backend/app/src/app/cli/cli.py`.

## Shared model

A **work unit** is one synchronous call. It returns `True` to run again immediately, or `False` to wait for the wakeup interval.

A **supervised service** is the `bgt` service loop on the supervisor's daemon thread. When a work unit raises, the supervisor starts that loop again after a backoff.

The interactive session runs as one work unit on the `supervisor-<name>` thread. `_session_work` runs `anyio.run(_run)`. On a clean return it sets `session_done` and waits on `release_worker`. `main` waits on `session_done`, sets `release_worker`, and calls `stop`, so the interval does not start another session. A turn that raises leaves `_session_work`, and the supervisor starts a new in-memory session after its backoff. Ctrl+C on `main` closes stdin, and the blocked `input` raises `EOFError`, which `_run` treats as a quit. The collapsed-run retry, two further attempts of the `run_turn` that raised with the finished tool step kept, is not this path.

## Gaps

- The person asked to run it interactively. This session treats that as the whole `_run` session being one work unit. They have not confirmed that, and one work unit per typed line would restart on a different boundary.
- Resolved for the injected case: a `KeyboardInterrupt` on the main thread's `Event.wait` closed stdin and the session's `input` raised `EOFError`. A keypress Ctrl+C in a console was not sent.
- "that noy" was their answer when asked which decision the understanding would change. The later words "implement it" are the choice this session followed.
- The person said "implement it". The code in `backend/app/src/app/cli/cli.py` now runs the whole `_run` session as one work unit. They did not restate the model, and they did not say whether that request also included the collapsed-run retry. The implementation does not retry a collapsed `run_turn`.
- A probe on 2026-10-28 replaced `_run` and `setup_observability` and called `main`. A session that returned ran once, `main` returned in 0.052 seconds, and a further 2.4 seconds did not start a second session. A session that raised `RuntimeError` logged `supervisor.restarting` and then a second session returned; `main` ended with the call count at 2. A `KeyboardInterrupt` raised from the main thread's `Event.wait` while the session was blocked in `input` closed stdin, `input` raised `EOFError`, and the service stopped after one session. That interrupt was injected in-process. A console Ctrl+C was not sent.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate the shared model. | The whole interactive session is one work unit on the supervisor thread. `main` stops the service after a clean return. A raised session is started again by the supervisor. Ctrl+C on `main` closes stdin. The collapsed-run retry is a separate mechanism. | | |
| When you ask if it is difficult, do you mean the prompt wrapper, or also the collapsed-run retry? | The implemented path is the prompt wrapper. The collapsed-run retry is two further attempts of the `run_turn` that raised, with the finished tool step kept. | | |
| What would you decide? | Their choice. | "implement it" | The interactive wrapper is implemented. They did not restate the model. |

## Handoff for a human ADR

No ADR file is written. The person chose an implementation with "implement it".

Context: `app.cli.cli.main` hosts the interactive session. `_run` is that session. `bgt.SupervisedService` runs a synchronous work unit on a daemon thread and restarts the loop when the unit raises.

Drivers, in their words: "that I can run the runtime wrapped in a supervised job by using bgt", and "so could I runt it interactively as a bgt supervisedservice?"

Considered options: pass async `_run` straight to the service; run the whole session as one synchronous work unit and stop from the main thread; also implement the collapsed-run retry inside that wrapper.

Chosen: the whole session as one work unit, with `stop` called from the main thread. Their words: "implement it". Because they asked to run it interactively as a supervised service, and the collapsed-run retry was described as separate work.

Consequences: a clean quit stops the service. A raised session starts a new in-memory session after the supervisor backoff. Ctrl+C on the main thread closes stdin. A collapsed `run_turn` is not retried twice, and a finished tool step is not kept.

Confirmation: they did not restate the model. The alignment check stays open.

More Information, in their words:

> that I can run the runtime wrapped in a supervised job by using bgt

> that noy

> so could I runt it interactively as a bgt supervisedservice?

> is it difficult to implement?

> implement it

Open questions: whether they also wanted the collapsed-run retry. A real console Ctrl+C was not sent; the interrupt was injected as `KeyboardInterrupt` from the main thread's `Event.wait`.
