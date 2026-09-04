# The Agent Stack — Part 5: Context, Retrieval, and Memory

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-5-context-retrieval
- **Published:** 2026-04-27
- **Fetched into this repo:** 2026-07-22

## Thesis

"Context is not what the model knows. Context is the bounded working set the runtime assembles for one turn." Retrieval brings evidence into that turn. Memory brings durable state back into that turn. Session history preserves continuity across turns. These are related but not interchangeable — the model only ever sees the request payload, never the full system state.

## The four things kept distinct

- **Session history** — the durable, chronological record (source material). *Not* the same as prompt context.
- **Prompt context / working set** — the derived, selected subset actually sent to the model this turn.
- **Retrieval** — brings external evidence (docs, tickets, code, search results) into the turn. Returns *candidate* evidence, not truth.
- **Memory** — durable state persisted outside the model and deliberately re-injected later. Not model learning (weights don't change), not just the transcript.

> "Prompt context is derived state. Session history is source material." Compaction should mean "don't send all of this right now," never "erase the only record of what happened."

## Retrieval brings evidence, not authority

A retrieved chunk can be relevant and still wrong, stale, unauthorized for this user, the right document but wrong version, or untrusted text that shouldn't steer the model. A similarity score means "this looks related," not "this should govern the answer." Retrieved evidence should carry: source, owner/tenant, version, freshness, permissions, retrieval reason, confidence, and provenance (user-provided vs. system vs. external). "A retrieval layer solves access. A context layer decides whether accessed evidence should influence the model."

## Memory is state with a lifecycle

"A transcript says what happened. A memory says what the system chose to preserve from what happened." A memory layer must decide: what's worth extracting, explicit instruction vs. inferred preference, scope (user/session/project/tenant/application), source, conflict resolution against older memories, freshness/expiry, who can inspect/delete, and where it re-enters context. A vector database supports memory (helps find related records) but doesn't *own* memory lifecycle — it can't decide whether an old preference should still apply, or resolve a conflict between two memories.

> "Retrieval solves access. Memory solves ownership."

## Context assembly is hot-path; memory maintenance is (mostly) background

Context assembly (fetch session, load workflow state, retrieve docs/memories, filter by scope, trim history, attach tool defs, format the request) is hot-path work — slow or wrong here directly hurts the user. Memory extraction, consolidation, index refresh, compaction, and expiry can usually happen *after* the response, as background jobs — unless the user explicitly demands immediate persistence ("remember this before we continue"). Blocking every turn on memory maintenance is why agents "feel smart in a notebook and sluggish in production."

## Long context and caching don't remove the job

A bigger context window is more room, not a decision-maker — it doesn't know which session belongs to the user, which document superseded an old one, or whether a memory was weakly inferred vs. explicitly stated. More room can mean more noise/cost/latency and buried relevant facts ("Lost in the Middle" — performance degrades when relevant info sits in the middle of long inputs). Prompt caching makes repeated context cheaper/faster; it does not decide what should be remembered, own deletion, resolve conflicts, or validate scope. "Caching optimizes reuse. Memory governs persistence."

## Why this hands off to Part 6

Context determines what the model can *reason over*. Tools determine what the model can *ask the system to do*. A retrieved policy can inform an answer but doesn't authorize an action; a memory can shape personalization but doesn't grant identity.

## Failure modes named

1. **Transcript stuffing** — appending history until the request is slow/expensive/noisy. Works in demos, fails in long-running systems.
2. **Compaction as deletion** — trimming the model-visible set accidentally destroys source material needed for audit/recovery.
3. **Retrieval as truth** — treating a highly-ranked chunk as authoritative just because it ranked highly.
4. **Missing scope** — a memory/document enters the prompt with no owner boundary → personalization becomes leakage.
5. **Vector database as memory** — an index is useful but isn't the whole layer (still need extraction, conflict handling, provenance, TTL, deletion, audit).
6. **Implicit memory writes** — persisting something just because the model/tool/user said it once, without deliberate lifecycle decision.
7. **Hot-path memory maintenance** — blocking every turn on extraction/consolidation/writes.
8. **Prompt cache mistaken for memory** — a cached prefix doesn't create durable state ownership.
9. **Memory poisoning** — persistent memory is a future influence channel; malicious/false info stored once can affect turns long after the original input is gone. A trust boundary, not an unsafe-by-default thing.

## Builder checklist from the article

1. Name the source of truth for session state (transcript, event log, working state need an owner).
2. Treat prompt context as derived state — inspectable, reproducible, separate from stored history.
3. Put scope on every retrieved/remembered item (user/tenant/session/project/application) — never implicit.
4. Track provenance and freshness — where context came from, when created, why included.
5. Separate retrieval policy from memory lifecycle.
6. Make memory writes explicit — not every model statement or tool output becomes durable state.
7. Keep expensive maintenance off the hot path unless the current turn needs the result immediately.
8. Audit the assembled working set — "the useful question is not only what the model said, it's what the runtime put in front of it."

## Series roadmap

Part 6 next: Tools, MCP, and Capability Surfaces — from "what does the model see" to "what is the model allowed to call, under whose authority, and with what limits."
