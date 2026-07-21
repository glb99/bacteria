# The Agent Stack — Part 3: Control Planes, Sessions, and State Ownership

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-3-control-planes
- **Published:** 2026-04-13
- **Fetched into this repo:** 2026-07-20

## Thesis

Continuity (what the user experiences) is not control (what the system can resume without guessing). The control plane's job: take an incoming event, resolve it to a session, load the authoritative record and working state, decide what continuation handle is valid, and hand a bounded state view to the runtime for the current turn. That is distinct from the runtime, which assembles the turn, calls the model, runs tools, streams results, and emits new state.

## A session is an isolation boundary, not just history

A session is not history replay — it's the isolation boundary around one live interaction. One user can have many sessions; one session can survive many turns; one run is only one execution segment inside a session.

A session boundary does two jobs:
- **Continuity** — a durable place for the interaction to live across turns.
- **Controlled mutation** — a place where new events commit in a trustworthy order, scratch state changes without leaking into unrelated work, and compaction/replay can happen without treating the whole transcript as the prompt.

Session state is not a convenience cache (a cache is easy to rebuild; a live interaction record is not). The operational question on resume isn't "what was the last message" but "which committed state does this next decision inherit?"

**Session ownership stays separate from authorization** — knowing which record to load is not knowing which resource/tool call is allowed.

## "State" hides three different jobs

1. **Transcript state** — durable record of what happened (messages, tool calls, outputs, approvals, results).
2. **Working state** — mutable scratchpad for the live interaction (progress flags, partial task data, checkpoint-able execution state).
3. **Memory** — durable state stored *outside* the live session, reintroduced later, deliberately.

The model sees a **prepared view**, not the canonical record — compaction/filtering/selective replay are normal context prep, not data loss, once this distinction is clear.

## Resume, retry, and correction expose the real architecture

An interrupted run (pause for approval, then a correction arrives) forces an explicit ownership decision: resume the old run, append a correction to the same session, or fork from the last stable point. This is an ownership question, not a model question. Every serious system needs an explicit answer to: What is the active run? Which state is authoritative? What is allowed to continue?

## Failure modes named

1. Using a user ID as the session key — unrelated tasks share transcript/scratch state.
2. Letting worker-local memory become the source of truth — a restart loses state silently.
3. Treating stored transcript as identical to model input — nobody can explain what the model actually saw.
4. Mixing continuation mechanisms without a rule — history lives in two places, no policy for which wins.
5. Assuming retry/rewind undoes side effects — it usually doesn't; session state and outside-world actions don't share rollback semantics.
6. Collapsing authorization into continuity — same session ≠ same permissions.

## Builder checklist from the article

- Make session identity explicit, and keep it separate from user identity.
- Name the authoritative transcript store.
- Name the authoritative working-state store.
- Decide what resumes a run (session ID, response chain, checkpoint, workflow run, etc.).
- Treat prompt context as a prepared view, not the canonical record.
- Make retry, resume, correction, and fork semantics explicit before you need them.
- Keep external side effects on a different mental shelf from rewindable session state.

## Series roadmap

Part 4 next: Runtimes, Workflows, and Durable Execution — where waits, retries, and resumes stop being policy questions and start becoming machinery.
