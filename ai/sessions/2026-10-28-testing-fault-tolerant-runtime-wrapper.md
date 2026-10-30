---
date: 2026-10-28
status: aligned
question: "How should we design tests for a fault-tolerant runtime wrapper as a prototype?"
adr: ""
---

# How should we design tests for a fault-tolerant runtime wrapper as a prototype?

## Why this session

You've built a `bgt` supervised service framework that wraps the agent runtime and adds fault tolerance (retries, backoff, supervision). Before committing to a test strategy for this prototype, you want to think through how a senior engineer would approach it.

## Starting model

| Prompt | Answer |
| --- | --- |
| What do you currently believe about testing this fault-tolerant wrapper? | Integration tests of the full wrapped runtime. `bgt` is an external library from PyPI already tested, so I won't test it. This is a first approach to decide if I'll use `bgt` or develop a custom solution. |
| What decision would that understanding change? | Whether `bgt` is the right mechanism for fault tolerance, versus building a custom solution. |

## Evidence

- From 2026-10-27 session: the retry contract is precise — retries cover every exception from `run_turn`, 2 further attempts, tool calls registered as done only after handler returns. A retry must not re-execute a tool that succeeded.
- From 2026-10-28 session: `bgt.SupervisedService` runs a work unit on a daemon thread, restarts the loop on exception with backoff, and provides `stop(timeout)` for shutdown. `_session_work` wraps `anyio.run(_run)` and `main` waits on completion before calling `stop`.
- From 2026-10-28 supervisor probes: a work unit can raise (supervisor restarts), block indefinitely (stop timeout returns False), raise during shutdown (RuntimeError on thread.join), and return cleanly (wait for next interval). The supervisor logs `loop_crashed`, `restarting`, and `loop_crashed_during_shutdown`.
- A prototype's role is to answer whether `bgt` fits or whether custom code is needed. The test suite for a prototype should reveal where `bgt` works and where it breaks.
- Unit tests of `bgt` exist in its distribution (`bgt>=26.2.0`). Testing `bgt` again is redundant. Integration tests check whether the wrapper and the runtime coexist correctly.
- The retry contract (2 attempts, tool step registration) is not yet implemented. The first-pass tests should specify what must happen, so implementation can follow.
- From probes: `bgt` handles restarts cleanly but does not natively support retrying the same work unit twice; a new exception always triggers a full restart. The 2-attempt retry of the same `run_turn` call is separate code inside the wrapper.

## Inferences

- Because this is a prototype to decide whether to use `bgt` or build custom, the test suite should focus on the integration boundary: does the wrapped runtime behave correctly under faults? Does `bgt` provide what the wrapper needs?
- A senior engineer would not test `bgt`'s internal supervisor loop or exception handling (that's its responsibility). They would test whether the wrapper's observable behavior matches the contract: input → work unit runs → output or exception → wrapper handles it correctly.
- The critical tests are fault injection tests: deliberately break the runtime at different points (model call fails, tool fails, session setup fails, tool handler crashes mid-execution) and verify the observable outcome (retry count, transcript state, tool execution count, etc.).
- For a prototype, tests should be focused: test the faults that would change the decision (can the wrapper get the retry behavior right? can `bgt` handle the restart without corrupting state? does the daemon thread cleanup work?). Don't over-test happy paths; assume the runtime works.
- The test design should expose where `bgt` fits and where it doesn't: do daemon threads cause cleanup issues? Does `stop(timeout)` work reliably? Does the backoff configuration matter? These answers feed the decision to keep `bgt` or build custom.
- Each test should be deterministic fault injection (not random) so you can assert exact retry counts, verify transcript entries, and check that tools aren't re-executed. Observable signals are logs, metrics, session state, and the returned result.
- The wrapper's integration boundary (the public interface: `SupervisedService.start`, `.stop`, `.is_running`) should be tested for correctness under faults, not just happy paths.

## Shared model

**Integration testing the wrapped runtime** means testing the observable behavior of `run_turn` wrapped in `bgt.SupervisedService`, given faults. The wrapper must meet the retry contract (2 further attempts, tool steps registered as done only after handler returns) and must not corrupt session state or re-execute succeeded tools.

**For a prototype**, the test strategy answers a specific question: does `bgt` provide the mechanisms the wrapper needs, or does custom code become necessary? This focus shapes what to test:

- **Test the critical path:** model calls that fail, tool calls that fail, handlers that crash mid-execution. Verify the wrapper handles each with the right retry count and observable state (transcript, session, tool execution count).
- **Test the integration boundary:** `SupervisedService.start`, `.stop`, `.is_running` under faults. Verify backoff, supervisor restarts, and daemon-thread cleanup work as expected.
- **Don't test `bgt` itself:** it has its own test suite. Test only whether the wrapper and runtime coexist correctly with `bgt`'s behavior.
- **Use deterministic fault injection:** inject a known failure (a mock that raises on the nth call), run the wrapper, and assert the observable outcome (retry count, transcript entries, tool call count). Not random chaos.
- **Observe through signals:** logs, metrics, session state (transcript), returned results, exceptions. These tell you whether the retry happened, how many times, and whether tool steps were registered.

**TDD approach:** Write tests first to specify the retry contract. The tests define what must happen when a fault occurs, before the retry implementation exists.

**Implementation-agnostic design:** The retry mechanism starts outside the work unit (`bgt` supervisor restarts), but the code must allow it to move inside later if needed. Achieve this by:
- Defining a `RetryPolicy` abstraction (interface or protocol) for how retries work
- Current concrete implementation: `SupervisorRetryPolicy` (relies on `bgt`)
- Future alternative: `WrapperRetryPolicy` (catches exceptions inside the work unit)
- Tests specify the *observable behavior* ("retry happens twice"), not the implementation mechanism. Tests don't change when you swap implementations.

The goal is to learn whether `bgt` fits this use case and to build code that's maintainable and flexible enough to evolve as you learn.

## Gaps

- Resolved: write tests first (TDD) to specify the contract before implementation.
- Resolved: start with `bgt`'s supervisor for restarts (outside the work unit), but design the code to allow moving that logic inside later.
- Remaining open question: what is the acceptable latency for each retry attempt? (Affects test timeouts and backoff configuration). The 2026-10-28 supervisor probes showed backoff in the range of 0.1 seconds. Is that acceptable for the wrapped runtime, or should it be tunable?

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Does this testing strategy focus on the right thing? | Integration tests of the wrapped runtime under faults, using deterministic fault injection to verify retry behavior and state correctness. Not testing `bgt` itself or over-testing happy paths. | "yes" | yes |
| Should tests be written before or after implementing the retry contract? | This determines the role tests play: specification (TDD) or verification (after). For a prototype, which would be more useful? | "TDD" | yes |
| Is the retry mechanism inside the work unit (the wrapper retries the same `run_turn` call), or outside (bgt supervisor restarts)? | For now, rely on `bgt`'s supervisor restarts. But the design must allow the retry logic to move inside the work unit later if needed. Design it like a senior engineer: implementation-agnostic, easy to swap. | "for now as we are using bgt, outside, but I do not discard that mechanism to be inside the run, I would like to do it as a senior engineer" | yes |

## Handoff for a human ADR

**Context:** You're building a fault-tolerant wrapper around `run_turn` using `bgt.SupervisedService`. The retry contract (2 further attempts, tool steps registered only after handler returns) is decided. The retry mechanism starts outside the work unit (via `bgt`'s supervisor restarts) but may move inside later.

**Design principle:** Test the observable behavior (what happens), not the implementation mechanism (how it happens). This keeps tests flexible as the mechanism changes.

**TDD approach — test categories:**

1. **Fault injection tests (most important):** Specify what happens when `run_turn` raises at different points.
   - Model call fails mid-execution (e.g., `ServingError`)
   - Tool call fails mid-execution (e.g., handler raises)
   - Session setup fails (e.g., `UnknownSessionError`)
   - Verify: retry count, transcript entries, tool execution count (no re-execution), final result or exception

2. **Tool step registration tests:** Verify the contract that tools aren't re-executed on retry.
   - Mock a tool handler that fails on the first attempt but succeeds on retry
   - Assert the tool is called once per attempt, total call count = retry attempts
   - Assert the transcript shows the correct number of `tool_call` entries after a successful retry

3. **State isolation tests:** Verify retries don't corrupt session state.
   - Run a failing work unit once, inspect session state
   - Run the same failing unit again (new session), verify state is clean (no ghost entries from the previous failure)

4. **Integration boundary tests:** Verify the wrapper's public interface under faults.
   - `SupervisedService.stop()` while a work unit is retrying
   - Backoff timing (does supervisor wait the right amount before restart?)
   - Daemon thread cleanup (does the process exit cleanly after stop?)

**Implementation-agnostic design:** To allow the retry mechanism to move from outside (supervisor) to inside (wrapper), use this pattern:
   - Define a `RetryPolicy` abstraction (interface, protocol, or strategy object)
   - Current implementation: `SupervisorRetryPolicy` (relies on `bgt` restarts)
   - Future implementation: `WrapperRetryPolicy` (catches exceptions inside the work unit)
   - The work unit's observable behavior stays the same; tests don't change

**Concrete test file structure:**
```
tests/
  test_wrapped_runtime_faults.py
    class TestModelCallFaults
      test_model_serving_error_retry_succeeds()
      test_model_serving_error_exhausted_retries()
    class TestToolCallFaults
      test_tool_handler_raises_retried()
      test_tool_not_reexecuted_on_retry()
    class TestSessionSetupFaults
      test_unknown_session_error_retried()
    class TestIntegrationBoundary
      test_stop_during_retry()
      test_backoff_timing()
      test_daemon_cleanup()
    class TestStateIsolation
      test_failed_session_clean_on_retry()
```

**Observable signals for assertions:**
- `run_turn` return value or exception
- Session transcript (count of `message`, `tool_call`, `run_error` items)
- Tool execution count (via mock or spy)
- Logs (supervisor logs `loop_crashed`, `restarting`, retry count)
- Metrics (if added) or timing (backoff duration)
