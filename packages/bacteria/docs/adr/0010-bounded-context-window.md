# 0010 — Assemble context as a bounded recent-message window

## Status

Accepted — 2026-08-06

## Context

The default way to build an agent's context is to append each turn to a list and
send the list. It works, right up until it does not: cost and latency climb turn
over turn, the model's attention spreads across material that stopped being
relevant twenty turns ago, and eventually one request overflows the window and
the conversation breaks entirely — all at once, with no warning.

The sophisticated remedy is summarization: compact old turns into a summary,
keep recent ones verbatim. It buys effectively unlimited conversation length and
introduces a failure of its own. A summarizer decides what to discard, silently,
and when it discards the wrong thing the model behaves as though something never
happened. That failure is much harder to diagnose than running out of window,
because nothing reports it.

There is also a related question the same layer has to answer: memory is not
conversation, and if it is appended to the message list the model cannot tell a
fact the system chose to preserve from something the user just said.

## Decision

Keep the last N messages (default 20), drop the rest. No summarization, no
compaction, no relevance scoring.

Include only `message` transcript items. Tool-call records are filtered out —
they exist so a human or an audit can reconstruct what ran, and replaying them as
conversation would show the model a garbled second version of an exchange it
already saw as tool-result blocks.

Always include the new user message, regardless of the window.

Surface memory through the system prompt, never in the message list. Include each
entry's `reason` alongside its value, so the model receives a fact with its
provenance rather than a bare assertion.

Own this in `context/assembly.py` rather than in the runtime. Deciding what is
relevant and what it costs is a policy question, and policy questions get a
module.

## Consequences

Context size is bounded and predictable. The failure that actually happens is
fixed, without adopting a failure mode that is worse to debug.

The strategy is legible: anyone can read fifteen lines and know exactly what the
model sees.

Long conversations lose their beginning, with no notice to either party. This is
the real cost, and it is accepted because the loss is *comprehensible* — "we keep
the last twenty messages" is something a user can be told, where "a summarizer
dropped something" is not.

The window counts messages, not tokens. Twenty long messages cost far more than
twenty short ones, so the bound is on count rather than on spend. A real budget
needs a tokenizer per provider.

Retrieval attaches here when it exists. When it does, retrieved content must
arrive as candidate evidence rather than authority — assembled context is a claim
about relevance, and a retrieved passage carries no more weight than the
retriever's confidence in it.
