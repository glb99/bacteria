# 0012 — Commit evidence even when a run fails

## Status

Accepted — 2026-08-06

## Context

The natural way to write `run_turn` is to do the work, collect the results, and
commit at the end. It is clean, it has one commit point, and it is wrong in a
specific way that only shows up when something breaks.

If any step raises — a rejected tool call, a handler failure, a model call that
fails on credentials — the exception propagates out before `commit` runs. The
session then contains nothing. Not the tool attempt, not the error, not even the
user's message. The only record of what happened is a stack trace in a terminal
that will be closed.

This was not hypothetical. Running the CLI for the first time with no API key
produced exactly this: a failure with no evidence, and the session as empty
afterwards as before. The runs with nothing to show for them were precisely the
runs worth investigating.

A related gap in the same area: tool-call transcript records held the *output*
but not the `input`. What came back was recorded; what was asked for was not.

## Decision

Wrap the turn. Any exception appends a `run_error` transcript item, commits
everything accumulated so far, and re-raises.

Accumulate evidence as the turn progresses rather than assembling it at the end.
This is why `_execute_tool_calls` takes the evidence list as a parameter and
appends to it — including on the failure path, before the exception leaves the
method — instead of returning items the caller would never receive.

Record both sides of a tool call: `input` and `status` alongside `output` or
`error`.

Re-raise rather than swallow. The caller still sees the failure loudly; the
session now also has a permanent record of it. Both, not one.

## Consequences

A failed run is diagnosable after the fact from session state alone. The
transcript shows the user's message, any tool attempted, and why it stopped.

The two failure routes are covered by separate tests, because they enter the
handler differently: a rejected tool call, and a model call that fails before any
tool exists.

`run_turn` has a broad `except Exception`, which is normally worth objecting to.
It is justified here by what it does — it does not suppress or classify, it
records and re-raises — but it does mean an unexpected exception type gets
stringified into a transcript item rather than being handled deliberately.

Passing a mutable list into `_execute_tool_calls` for it to append to is less
obvious than returning a value, and is the price of the evidence surviving a
raise. The parameter is named and documented for that reason.

There is no redaction. Tool inputs are recorded verbatim, so a tool taking
sensitive arguments would write them into the transcript. Acceptable while state
is in-memory and single-user; it becomes a real problem the moment the store is
persisted. Trace and audit are also one record here, which is right for one
developer and wrong once those audiences differ.
