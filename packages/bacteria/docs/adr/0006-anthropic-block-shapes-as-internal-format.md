# 0006 — Use Anthropic block shapes as the internal message format

## Status

Accepted — 2026-08-06

## Context

[ADR 0005](0005-narrow-model-protocol.md) makes the model *call* swappable. It
says nothing about the messages crossing that call, and something has to decide
their shape.

Two options. A neutral internal format, translated by every client including the
first — clean symmetry, no vendor privileged. Or adopt one vendor's shapes as
the internal format, and have other clients translate to and from them.

The neutral format is more principled and costs more than it looks. It is a
third format to design, document, version, and keep in sync with two moving
vendor formats. Its correctness is only testable through the clients that
consume it, so it adds a layer without adding a place to catch bugs. And it
would have been designed by generalizing from a single known vendor format,
which makes "neutral" aspirational.

## Decision

The runtime, the context assembler, and the tool loop all construct Anthropic's
shapes: string content or a list of `{"type": "text" | "tool_use" |
"tool_result", ...}` blocks. That is the internal format.

Non-Anthropic clients translate in both directions, entirely inside their own
module. `GeminiClient` is the worked example.

Say so plainly in `model/protocol.py` rather than implying neutrality the
protocol does not provide.

Carry the one piece of genuinely provider-specific state through a generic
escape hatch: `ToolCall.provider_data`, an opaque dict the runtime forwards and
never reads. Deliberately not named after any provider, so a module that does
not care about it need not know it exists.

## Consequences

The Anthropic client is nearly free — its translation is close to a copy. The
Gemini client carries the whole cost, and it is not small: role remapping
(`assistant`/`user` versus `model`/`user`/`tool`), a pre-pass to recover
function names because a `tool_result` block carries only an id while Gemini
keys responses by name, and schema field differences.

The asymmetry is a standing tax on every additional provider, and it will be
mistaken for Anthropic being "the real one". The protocol docstring names this
directly to keep it from being discovered by surprise.

`provider_data` turned out to be load-bearing rather than speculative. Gemini
attaches a `thought_signature` to function-call parts and rejects a follow-up
request that arrives without it — found only against the live API, after every
mocked test passed. A narrower fix was tried first (disabling thinking) and
failed, because the requirement holds whether or not thinking is enabled.

Reversal stays open. Introducing a neutral format later means rewriting the
Anthropic client's translation and the runtime's block construction — real work,
but bounded and confined to modules that already exist.
