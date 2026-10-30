---
date: 2026-10-27
status: gaps
question: "If the agent run collapses when running, does it retry?"
adr: ""
---

# If the agent run collapses when running, does it retry?

## Why this session

The person asked whether a running agent run retries after it collapses. They believe it does not. They want to give the agent robustness, starting with a retry when a run collapses.

## Starting model

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "I think that not" — a collapsed agent run does not retry. |
| Which decision would this understanding change? | "that it does" — the decision to change is that a collapsed agent run retries. |

## Evidence

- An agent run is `run_turn` in `backend/app/src/app/agent/runtime.py`. It creates one `run_id`, loads the session, retrieves, assembles context, sends to the model, and runs a tool loop bounded by `MAX_TOOL_ROUNDS` (3). There is no retry around `run_turn` and no retry around the tool loop. If the loop does not stop because the model returned no tool calls, it raises `RuntimeError` (`tool loop exceeded {MAX_TOOL_ROUNDS} rounds`) before the transcript commit.
- The transcript commit in `run_turn` runs only after that loop finishes. An exception from the model call or from a tool call leaves the function before `session_repository.commit`.
- `execute_tool_call` in `backend/app/src/app/agent/tools.py` calls the handler once. An unknown tool becomes `ToolExecutionError`. There is no second attempt.
- The CLI loop in `backend/app/src/app/cli/cli.py` awaits `run_turn` once per line of input. Its docstring says exceptions from a turn are not caught. The only exceptions that loop catches are `EOFError` and `KeyboardInterrupt` around `input`.
- `backend/app/src/app/cli/__init__.py` says an interface that decides when to retry has become a second runtime.
- `GeminiAgent.send` in `backend/app/src/app/llm/multimodal.py` retries one model call. `max_retries` defaults to 2 and is documented as additional attempts for `ServingError` only. The loop increments `attempt` after a `ServingError` and raises when `attempt > self.max_retries`, sleeping `backoff_seconds * attempt` between attempts (`backoff_seconds` defaults to 1.0). `_classify` maps `httpx.TransportError`, Gemini `ClientError` with code 429, and Gemini `ServerError` to `ServingError`. Credentials, asset-size, and other client or API errors are classified as something else and raised immediately.
- The word "collapse" does not appear in the agent runtime, the CLI, or the model client.
- `TranscriptItemKind` in `backend/app/src/app/agent/session.py` includes `"message"`, `"tool_call"`, and `"run_error"`. `run_turn` commits two items, both `kind="message"`: the user text, then the assistant text. Both commits are after the tool loop returns. No code under `backend/app/src` commits a `tool_call` or `run_error` item.
- `assemble_context` in `backend/app/src/app/agent/context.py` keeps only transcript items whose `kind` is `"message"`.
- The runtime's spans (`agent.session.load`, `agent.retrieval`, `agent.context.assemble`, `agent.model.request`, `agent.tool.execute`, `agent.transcript.commit`) are trace spans. The next `run_turn` does not read them.

## Inferences

- A collapse, taking the person's word to mean the run ending by an exception before `run_turn` returns, is not retried. The runtime has no retry of the run, and the CLI does not call `run_turn` again. That matches the starting belief. Evidence: `runtime.py`, `cli.py`.
- A transient serving failure inside one model call is retried by `GeminiAgent.send` before `run_turn` sees it as a failure. When those attempts are exhausted, `send` raises `ServingError`, `send_model_request` does not catch it, and that exception is then a collapse of `run_turn`. Evidence: `multimodal.py` and the single `model_client.send` call inside `send_model_request` in `runtime.py`.
- A model-call retry repeats `generate_content` for the messages already built. It does not reload the session, retrieve again, or execute tools again. A retry of `run_turn` would do all of those again. The note tool appends a line on each successful call (`tools.py`, `build_add_note_tool`), so a second pass through the tool loop would append again. Evidence: `runtime.py` tool loop, `tools.py`.
- The person's account of how a retry would know is: "because the run is divided in steps, and at the moment of the failure, the tool calling step is registered as already done." The current `run_turn` does not do that. A failure leaves no `tool_call` transcript item, and the next run reads messages only. Evidence: `runtime.py` commit site, `session.py` kinds, `context.py`.
- If a later change makes a collapsed run retry, the CLI module states that the interface is the wrong place for that decision. Evidence: `cli/__init__.py`. Where the retry would live is still open.
- The note tool writes the line and then returns the saved-note string. Evidence: `build_add_note_tool` in `tools.py`. `execute_tool_call` returns a `ToolResult` only after the handler returns. A raise inside the handler leaves `run_turn` with no `ToolResult`. Evidence: `execute_tool_call` in `tools.py`, and the tool loop in `runtime.py`.
- The person accepted the recommendation. Their words: "Yes, only after the handler returns." The note tool's effect is the write immediately before the return. A handler that applies its effect and then raises, before that return, is not covered by the registration rule. Evidence: `build_add_note_tool` in `tools.py`.
- The person chose to retry every exception that leaves `run_turn`. Their words: "All of them." The exceptions that can leave it include `ServingError` after the model-call retries, `CredentialsError`, `ContractError`, `AssetError`, `ModelError`, `ToolExecutionError`, an exception raised by a tool handler, `RuntimeError` when the tool loop passes three rounds, and `UnknownSessionError` from the session load. The same inputs produce the same `CredentialsError`, `ContractError`, unknown-tool `ToolExecutionError`, and tool-loop `RuntimeError` on the next attempt. Evidence: `multimodal.py` `_classify`, `tools.py` `execute_tool_call`, `runtime.py` tool loop, `session.py` `get_state`.

## Shared model

An **agent run** is one call to `run_turn`. A **collapse** is that call raising before it returns a `RunResult`. The person defined it that way: "I mean a run_turn raise." The code never uses the word collapse.

A collapsed run does not retry. The CLI does not catch the exception and does not start the run again. The person chose that the retry covers every exception that leaves `run_turn`, and that a collapsed run is retried 2 times. Their words: "All of them." "2 times." Two times means two further attempts after the attempt that raised.

A **model-call retry** is separate. `GeminiAgent.send` tries the same `generate_content` request again only when the failure is a `ServingError`: a transport error, HTTP 429, or a Gemini server error. The default is two additional attempts, with a linear backoff. The session load, the retrieval, and any tool calls already finished stay as they are. If those attempts still fail, `ServingError` leaves `send` and collapses `run_turn`. Any other model error, a tool error, and a tool loop that passes three rounds collapse the run on the first occurrence. A second call to `run_turn` would repeat retrieval and tool execution. The note tool appends on each success, so that second pass would append again. The person decided the retry must not do that: "No, it shouldn't." The person wants the run divided into steps, with the tool-calling step registered as already done at the moment of failure. Their words: "because the run is divided in steps, and at the moment of the failure, the tool calling step is registered as already done." They chose when that registration happens: "Yes, only after the handler returns." A raise inside the handler, before any effect, is not the step already done, so a retry may call the tool again. They then said an effect that lands and then raises would count as done. Their word: "yes." Asked how the retry would know, they said "I don't know," and then chose the runtime's signal: "Yes, only the handler return." The runtime registers the step done only when the handler returns. It does not infer an effect from the exception, so an effect followed by a raise is not registered and a retry may call the tool again. `execute_tool_call` receives either a return value or an exception. Evidence: `execute_tool_call` in `tools.py`. The transcript kind `"tool_call"` exists, and `run_turn` never commits one. On failure it commits nothing.

## Gaps

- Open: the code changed after this session. Commit `68e0cff` ("Implement runtime run with retries") adds `run_turn_with_retry` in `backend/app/src/app/agent/runtime.py`. It calls `run_turn` up to `max_retries + 1` times (default 3 attempts, so 2 retries) and retries only on `ServingError`. Every other exception is raised immediately. This contradicts the Evidence bullet "There is no retry around `run_turn`" and the chosen "every exception" decision. The wrapper has no step registration, so a retry re-executes tools that already ran. Its callers are `backend/app/src/app/script/supervised_job.py` and `backend/app/src/tests/agent/test_wrapped_runtime_fault_tolerance.py`. The CLI still calls `run_turn` once.
- Implemented: each tool result is committed as a `tool_call` item (with `run_id`) when its handler returns. `run_turn_with_retry` passes one `run_id` to every attempt, and `run_turn` reuses committed results for that run and call id instead of running the tool again. Tests: `tests/agent/test_runtime.py`. Open: the reuse is keyed by the provider's call id, so a provider that issues new ids on a retry would run the tool again. Open: a failure after the user item is committed but before the assistant item still duplicates the user message on retry.
- Open: `run_turn_with_retry` does not wait between attempts. `GeminiAgent.send` uses a linear backoff.
- Resolved: collapse means `run_turn` raises. Their words: "I mean a run_turn raise."
- Resolved: a retry after `run_turn` raises must not execute a tool that already ran. Their words: "No, it shouldn't."
- Resolved: the tool-calling step is registered as done only after the handler returns. Their words: "Yes, only after the handler returns." A raise inside the handler is not that step already done. The registration is still not in the code.
- The person first said a handler that applies its effect and then raises counts as done. Their word: "yes." The later choice governs the runtime: that call is not registered, because the only signal is the handler's return.
- Resolved: the runtime treats the handler's return as the only signal that the call is done. Their words: "Yes, only the handler return." An effect followed by a raise is not registered. A retry may call that tool again.
- Resolved: every exception that leaves `run_turn` is retried. Their words: "All of them." The same inputs produce the same credentials error, contract error, unknown-tool error, and tool-loop error on the next attempt.
- Resolved: a collapsed run is retried 2 times. Their words: "2 times." Read as two further attempts after the attempt that raised.
- The person waived restating the shared model. Their words: "I don't need to restate the model."
- `cli.py` says a failed turn's evidence is already committed before the exception reaches the CLI. `run_turn` commits only after the tool loop returns. That docstring was not checked against a test. It does not change the retry finding.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate what a collapsed agent run does. | A collapse is `run_turn` raising before it returns. That run is not started again. A `ServingError` inside one model call is retried by `GeminiAgent.send` and is not a retry of the run. | "I don't need to restate the model." | waived |
| When you say the run collapses, do you mean `run_turn` raises, or a transient serving failure on one model call? | A collapse is `run_turn` raising before it returns. | "I mean a run_turn raise." | yes |
| What would you decide? | Their choice. | "I want to give the agent robustness, I am thinking about starting by implementing a retry mechanism in the case the run collapses." | |
| When `run_turn` raises after a tool has already run, should the retry execute that tool again? | Their choice. The code today would execute it again, because the tool call is not committed. | "No, it shouldn't." | |
| How should that retry know the tool already ran? | Their account, checked against the code. | "because the run is divided in steps, and at the moment of the failure, the tool calling step is registered as already done." | The account is their mechanism. The code does not register that step. |
| Should every exception that leaves `run_turn` be retried, or only some of them? | Their choice. | "All of them." | yes |
| How many times should a collapsed run be retried? | Their choice. Read as two further attempts after the attempt that raised. | "2 times, and I don't need to restate the model." | yes |
| A handler that applies its effect and then raises, before the return: should that call count as done? | Their choice. | "yes." | yes |
| How should the retry know the effect was applied? | The handler's return is the only signal. | "I don't know." Then: "Yes, only the handler return." | yes |
| When the failure is inside the tool handler, before it returns, does that step still count as already done? | Register the step done only after the handler returns. | "Yes, only after the handler returns." | yes |

## Handoff for a human ADR

No ADR file yet. One record this session can feed.

Context: `run_turn` does not retry when it raises. The CLI does not catch that exception or call `run_turn` again. `GeminiAgent.send` already retries one model call on `ServingError` only, default two additional attempts. The interface module says deciding when to retry there would make the CLI a second runtime.

Drivers: the person believes a collapsed run does not retry. They want to give the agent robustness. Their words for the first step: "I am thinking about starting by implementing a retry mechanism in the case the run collapses."

Considered options: not enumerated by the person. The code distinguishes a retry of the whole run from a retry of one model call. `GeminiAgent.send` already retries `ServingError`.

Chosen: start robustness by implementing a retry when `run_turn` raises. The retry covers every exception that leaves `run_turn`. A collapsed run is retried 2 times, read as two further attempts after the attempt that raised. The retry must not execute a tool that already ran. The run is divided into steps, and the tool-calling step is registered as done only after the handler returns. Because-clause, in their words: "I want to give the agent robustness," "All of them," "2 times," and "Yes, only after the handler returns." A raise inside the handler, before any effect, is not that step already done, so a retry may call the tool again. The runtime registers that step only when the handler returns. Their words: "Yes, only the handler return." An effect followed by a raise is not registered, and a retry may call that tool again. Their earlier "yes," that an effect followed by a raise counts as done, is not a signal the runtime uses.

Consequences: the code does not register that step today. `TranscriptItem` can be `kind="tool_call"`, and `run_turn` never commits one. A failure commits nothing, and `assemble_context` would ignore a `tool_call` item anyway because it keeps only `kind="message"`. A second `run_turn` from the same session state can request the tool again, and the note tool would append again. Putting the retry decision in the CLI would conflict with `cli/__init__.py`. A `ServingError` that reaches `run_turn` has already used the model-call retries inside `GeminiAgent.send`.

Confirmation: the meaning of collapse is confirmed, the tool-retry decision is confirmed, the handler-return rule is confirmed, the runtime's only signal is the handler's return, the retry covers every exception that leaves `run_turn`, and the retry count is 2. The person waived restating the shared model: "I don't need to restate the model." The step registration is not in the code. An effect followed by a raise is not registered.

More Information, in their words: "I think that not." "that it does." "I want to give the agent robustness, I am thinking about starting by implementing a retry mechanism in the case the run collapses." "I mean a run_turn raise." "No, it shouldn't." "because the run is divided in steps, and at the moment of the failure, the tool calling step is registered as already done." "I don't know, what do you think?" "Yes, only after the handler returns." "All of them." "2 times, and I don't need to restate the model." "yes." "I don't know." "Yes, only the handler return."

Considered for the unfinished tool call: register the step done only after the handler returns, so a raise inside the handler may be executed again on retry. Chosen by the person: "Yes, only after the handler returns." The other reading, not chosen, was to register the step done as soon as the handler is entered, including when it raises. A later choice covers the effect that lands and then raises: the person first said that call counts as done ("yes"), then chose the runtime's only signal: "Yes, only the handler return." The runtime does not register that call.

Open questions: none for the retry decision. A retry of every exception includes credentials errors, contract errors, unknown-tool errors, and a tool loop past three rounds. Those four come out the same on the same inputs. The retry still runs for them, twice. The `cli.py` docstring that says a failed turn's evidence is already committed was not checked against a test. `run_turn` commits only after the tool loop returns. That does not change the retry finding.
