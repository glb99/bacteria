# Bacteria — System Design Document

Source of truth for the architecture of the AI agent built in this repository. This document is written incrementally, one article section at a time, from *The Agent Stack* series (https://theagentstack.substack.com/p/the-agent-stack-part-1-a-systems). Each entry below records the team conclusion reached after discussing the corresponding article, not just a summary of the article itself.

See [`articles/`](../articles/) for the raw source notes per part, and [`CLAUDE.md`](../CLAUDE.md) for the working methodology.

---

## Status

| Part | Topic | Status |
|---|---|---|
| 1 | A Systems Map of Modern Agent Infrastructure | Recorded |
| 2 | Infrastructure, Models, and Inference | Recorded |
| 3 | Control Planes, Sessions, and State Ownership | Recorded |
| 4 | Runtimes, Workflows, and Durable Execution | Recorded |
| 5 | Context, Retrieval, and Memory | Recorded |
| 6 | Tools, MCP, and Capability Surfaces | Not started |
| 7 | Execution Surfaces, Identity, and Approval Boundaries | Not started |
| 8 | Observability, Evaluation, and Production Feedback Loops | Not started |

---

## Project Foundations

Cross-cutting decisions that aren't tied to a single article part.

- **Language: Python.** Dominant ecosystem for agent/LLM tooling (LangGraph, most MCP servers, Anthropic/OpenAI SDKs), and the article's own references (LangGraph, Temporal) are Python-friendly. Chosen over TypeScript/Node given our scope doesn't currently need a front-to-back web UI language.
- **Dependency/environment management: [uv](https://docs.astral.sh/uv/).** Manages the virtual environment, dependency resolution/locking (`uv.lock`, committed), and the Python interpreter itself. `pyproject.toml` stays standard (PEP 621), so this is a tooling choice, not a lock-in. Run tests/commands via `uv run ...`.
- **Package layout: single namespace package, `uv_build` backend.** Adopted from Hynek Schlawack's "My 2025 uv-based Python Project Layout for Production Apps" (YouTube). All code lives under one top-level package, `src/bacteria/` (`src/bacteria/model/`, `src/bacteria/session/`, `src/bacteria/runtime/`), imported as `bacteria.model.client` etc. — not as separate top-level packages (`model`, `session`, `runtime`), which risked colliding with other installed packages' namespaces and didn't read as clearly belonging to this project. Build backend switched from `setuptools` to `uv_build` (`[build-system] requires = ["uv_build>=0.11,<0.12"]`), since we're already all-in on `uv` and carrying a second build tool added nothing.
- **Pytest configuration and shared fixtures.** `[tool.pytest.ini_options]` in `pyproject.toml` (`testpaths`, `--strict-markers`, `--strict-config`, `--import-mode=importlib`) per current pytest best practice, rather than relying on implicit rootdir discovery. [`tests/conftest.py`](../tests/conftest.py) holds fixtures shared across test files (e.g. `make_fake_model_client`), auto-discovered by pytest without explicit imports — introduced once a fake model-client stand-in was needed in more than one test file. Deliberately **not** adopted: a blanket coverage-percentage gate (e.g. `--cov-fail-under`) — that would pressure padding out tests for decisions our own testing approach (see `CLAUDE.md`) says shouldn't get automated coverage at all (rationale/preference bullets, not load-bearing invariants).

---

## Part 1 — A Systems Map of Modern Agent Infrastructure

*Notes: [articles/part-1-systems-map.md](../articles/part-1-systems-map.md)*

### Discussion

Q&A recap from working through the article together:

- **Layer ordering isn't execution order.** The ten-layer list is an ownership inventory, not a pipeline. In the article's own request-path walkthrough, context assembly (layer 5) is invoked by the runtime (layer 3) *before* the model (layer 4) is called — so numeric position reflects "closeness to user-facing surface vs. raw infra," not who-acts-before-whom. Real execution order: control plane → runtime → context assembly → model call → tool/execution → observability, looped by the runtime.

- **Policy appears at both layer 2 and layer 8, and that's intentional, not redundant.** Layer 2 (control plane) *attaches* policy — resolves which policy set governs this session/run and tags the run with it; a lookup done once per run. Layer 8 (identity, trust, policy, approvals) *applies* policy — evaluates it against a specific action at the moment that action is about to execute, producing allow/deny/needs-approval. Attachment is static/per-run; application is dynamic/per-action.

- **This mirrors the article's explicit session ≠ authorization boundary.** Session tells you which interaction owns a turn (bookkeeping/routing). Authorization tells you whether a specific action is allowed right now (a security decision, re-checked per action). Collapsing them — treating "a valid session exists" as "therefore the action is allowed" — is how a session that was fine for read-only chat ends up triggering a destructive tool call, or how a session keeps acting on stale permissions after a user's access was revoked mid-session. They also fail differently: broken session → wrong context/lost state (UX bug). Broken authorization → did something it shouldn't have (security incident).

- **"Which state record is the source of truth?"** (one of the control-plane's resolution questions in the request-path walkthrough) means: when a run's state may exist in several places at once (in-memory process state, a DB row, a runtime checkpoint, a UI-side cache), which one is authoritative if they disagree? The control plane must name that record explicitly so resumes/retries read from the correct place instead of a stale derived copy. This will matter directly once we design state ownership (Part 3) and durable execution (Part 4).

### Team conclusion

We are building a **chat/task assistant with a small tool surface** — single-user, conversational, a handful of tools (not a long-running autonomous worker and not a multi-agent orchestration system). Given that scope, we will use the ten-layer stack as an **adaptable lens**, not a literal blueprint: it's the vocabulary and checklist we use to decide ownership boundaries deliberately, but we only build an explicit component for a layer when our scope actually needs one. Layers whose failure modes don't apply at this scope can stay implicit or be inherited from whatever runtime/framework we choose, as long as we've made that a conscious choice rather than an accident.

### Decisions for this project

- **Emphasize:** control plane / session ownership (layer 2), context/retrieval/memory (layer 5), tools/capability surfaces (layer 6), observability (layer 9). These map directly to a chat assistant with tools — we need to know what belongs in the hot-path context, keep tool schemas separate from execution, and have basic traces to debug behavior.
- **De-emphasize for now, revisit if scope grows:** heavy durable-execution/resumption machinery (layer 3) and formal approval workflows (layer 8) — a single-user assistant with a small tool surface doesn't yet need retry/resume-after-failure semantics or human-in-the-loop approval gates. We will still keep the *boundary* clear in code (e.g., don't let capability exposure silently double as execution authority) even if the enforcement is lightweight.
- **Infrastructure substrate (layer 10):** deferred — no conclusions until Part 2, which covers it directly.
- **Guiding rule carried forward:** even where we simplify a layer, keep the article's boundary pairs intact in our code and naming (session ≠ authorization, transcript ≠ context, capability ≠ execution, observability ≠ evaluation) so the system stays debuggable as scope grows later.

---

## Part 2 — Foundation Infrastructure, Models, and Inference

*Notes: [articles/part-2-foundation-infrastructure-models-inference.md](../articles/part-2-foundation-infrastructure-models-inference.md)*

### Discussion

- **Model provider:** discussed building against Anthropic directly vs. a provider-agnostic abstraction from day one. Settled on Anthropic direct, on the reasoning that a full swap-any-provider abstraction for a single-user assistant with no second provider in sight is premature abstraction — the article's "separate model/serving/contract choice" advice is a conceptual discipline (keep the concerns distinct in your head and in code boundaries), not a mandate to build a provider-swapping interface with no second implementation behind it.
- **Serving-system depth:** since we're calling a hosted API rather than self-hosting inference, queueing/scheduling/serving concerns are the provider's problem, not ours. We just need to be aware prompt caching exists and use it sensibly — no custom serving abstraction.

### Team conclusion

We build directly against the **Anthropic API** in Python, with **minimal serving-layer investment** (hosted API, no custom queueing/scheduling). We still honor the article's three-way split conceptually and structurally: model-calling code lives in its own module, isolated from the rest of the system, so the model asset / serving / interaction-contract concerns stay swappable in principle even though we're not building a swap abstraction now.

### Decisions for this project

- **Model client module:** isolate all direct Anthropic API calls (model asset + interaction contract concerns) behind one module — nothing else in the codebase talks to the API directly. → [`src/bacteria/model/client.py`](../src/bacteria/model/client.py)
- **No custom serving layer:** rely on the Anthropic API's own handling of queueing/scheduling; our code only needs basic retry/error handling around API calls, not a scheduler.
- **Tool calls treated as proposals, not execution** (per this part's boundary pairs): model output that requests a tool call must pass through explicit application-side authorization before anything runs — carries forward the layer-6/7 capability ≠ execution boundary from Part 1, now reinforced at the model-output level. Verified structurally today: `ModelClient` only reports `tool_calls`, it has no code path that executes anything. → ties to `src/tools/` and `src/execution/` (planned, to be detailed in Part 6/7)
- **Structured output treated as untrusted:** any JSON/schema output from the model gets validated by the application, not assumed correct — schema validity is shape, not truth. → [`src/bacteria/model/output.py`](../src/bacteria/model/output.py)
- **Caching:** if/when we use prompt caching, name explicitly which cache we mean (provider-side prompt cache vs. any app-level cache we might add later) rather than referring to "the cache" generically.
- **Error handling split by which of the three model-layer components failed**, instead of one generic "API call failed" exception — so retries and logging are correct and diagnosable per the layer that actually broke:
  - *Asset failure* (context window exceeded, unsupported modality, output too long) — not retryable as-is; requires reshaping the request.
  - *Serving failure* (rate limit, timeout, transient 5xx/overload) — retryable, with backoff.
  - *Contract failure* (malformed request, unexpected response shape) — an integration bug, not retryable blindly.
  → [`src/bacteria/model/client.py`](../src/bacteria/model/client.py), [`src/bacteria/model/errors.py`](../src/bacteria/model/errors.py) — distinct exception types per category, tested in [`tests/test_model_client.py`](../tests/test_model_client.py).
- **Retry logic must be side-effect-aware:** don't retry a request if a tool call from the prior attempt may have already executed — track whether a side effect occurred before treating a retry as safe. Implemented by scoping the retry loop to the literal API call only (identical request payload each attempt); tool execution lives in a separate, not-yet-built module (Part 6/7) that calls into this client, never the reverse — so this client structurally cannot retry-and-reexecute a tool. → [`src/bacteria/model/client.py`](../src/bacteria/model/client.py)
- **Structured output validated explicitly**, not trusted on schema-parse success alone (e.g. a pydantic model or equivalent check) before the rest of the app uses it. → [`src/bacteria/model/output.py`](../src/bacteria/model/output.py)

**Implementation status:** built and tested (5 load-bearing invariant tests in [`tests/test_model_client.py`](../tests/test_model_client.py) + 3 in [`tests/test_output_validation.py`](../tests/test_output_validation.py), all passing via mocked Anthropic responses). Not yet verified against a live API call — no `ANTHROPIC_API_KEY` was available in the dev environment at implementation time; do a real end-to-end call once a key is set locally.

---

## Part 3 — Control Planes, Sessions, and State Ownership

*Notes: [articles/part-3-control-planes-sessions-state-ownership.md](../articles/part-3-control-planes-sessions-state-ownership.md)*

### Discussion

- **"Proposed new items + state mutations" in the request-path diagram — is that a formal protocol?** No — the article doesn't define a wire protocol/schema for it. What the diagram shows is an architectural pattern: a two-phase separation between the runtime *proposing* new transcript items/state mutations (dashed arrow — a candidate, not yet authoritative) and a distinct, separate *commit* step that makes it canonical. This is the same "proposal ≠ execution" boundary from Parts 1–2, applied one level up to state writes themselves.
- **Is committing that state mutation something the agent (model) does, or something our infrastructure does?** Infrastructure, unambiguously. The model's output — including any "new transcript item" or "state delta" it produces — is just another proposal, no different in kind from a tool-call proposal. The model has no visibility into concurrency, ordering, or conflicting state, so it cannot be trusted with commit authority. Actually writing to the authoritative store must be deterministic, non-model code (control plane / state store), which can reject or reconcile a proposal against what the canonical record actually looks like at commit time (e.g., if a correction arrived mid-run).
- **Given our single-user chat/task-assistant scope, how much of this machinery do we build?** Minimal but explicit: one session store, a clear code-level separation of transcript state / working state / memory, but no multi-session routing and no fork/branch machinery — we don't yet have concurrent runs or multiple users to disambiguate between. We keep the propose/commit split conceptually honest (the runtime never writes directly to the canonical store) but implement it as a plain function call/return in our own code, not a formal protocol with its own schema — we have no concurrent writers to arbitrate between yet, so that formality would be premature.

### Team conclusion

We build a **single-session control plane**: one authoritative session/state store, with transcript state, working state, and memory kept as explicitly distinct concerns in code (never merged into one blob). The model/runtime never writes to that store directly — all state changes are proposals that pass through a dedicated, non-model commit step. We do not build multi-session routing, resume/fork branching, or a formal state-mutation protocol yet, since our scope (single user, no concurrent runs) doesn't need to disambiguate between competing continuations. If that changes later, the propose/commit separation we're building now is what makes adding those features additive rather than a rearchitecture.

### Decisions for this project

- **Single authoritative session/state store**, separate from any in-memory/runtime-local state. Runtime and model code treat it as the only source of truth; nothing else is allowed to be authoritative. → [`src/bacteria/session/store.py`](../src/bacteria/session/store.py)
- **Three explicitly separate concerns in code**, matching the article's three jobs of "state": transcript (durable record), working state (scratchpad/checkpoint data), memory (durable state reintroduced deliberately across sessions). Not modeled as one generic "state" blob. Memory is a stub for now — real design deferred to Part 5, flagged as provisional in code. → [`src/bacteria/session/store.py`](../src/bacteria/session/store.py)
- **Model/runtime output is always a proposal, never a direct write.** The commit step — actually persisting a new transcript item or state mutation to the authoritative store — is separate, deterministic, non-model code. `get_state()` returns a deep copy specifically so nothing can mutate authoritative state except `commit()`. → [`src/bacteria/session/store.py`](../src/bacteria/session/store.py)
  - **Amended during Part 4:** originally implemented as a two-step `propose()` → `commit(proposal)` API. Collapsed into a single `commit(session_id, new_transcript_items, working_state_updates)` after discussion showed the separate `propose()` method wasn't load-bearing — it did nothing beyond validating the session and building a plain dataclass. The invariant that matters (state only changes through one deterministic, non-model code path) is preserved just as strongly by `commit()` alone; a future staleness/conflict check would live inside `commit()` rather than in a separate step. Judged against the same premature-abstraction bar we applied to the Part 2 model-provider question — a "future seam" isn't reason enough to keep two methods when one already provides the real guarantee.
- **No formal state-mutation protocol/schema yet.** `commit()` is a plain function call in-process, not a message format with its own versioning — revisit only if/when we have concurrent writers or multi-session routing to arbitrate between.
- **Session identity kept explicit and separate from user identity**, even with only one user today, so the boundary exists in code before it's ever load-bearing.
- **Out of scope for now:** resume/retry/fork branching logic, multi-session routing. Noted as deliberately deferred, not overlooked — same treatment as durable execution/approvals deferred in Part 1.

---

## Part 4 — Runtimes, Workflows, and Durable Execution

*Notes: [articles/part-4-runtimes-workflows-durable-execution.md](../articles/part-4-runtimes-workflows-durable-execution.md)*

### Discussion

- **Why hold the line on durable execution?** Part 1 already deferred "heavy durable-execution/resumption machinery" for our single-user scope — this part doesn't overturn that, it tests it. Building persistence/replay/resume now would be solving a failure scenario (crash mid-long-running-workflow) we don't actually have yet, and doing durability *half-right* (getting retry/replay/resume/idempotency subtly wrong) is worse than clearly not having it — it creates false confidence. Holding the line means being explicit about what we have, the same way we were explicit that Part 3's session store is in-memory only.
- **Does holding the line mean skipping the article's concepts entirely?** No. Most of the builder checklist doesn't require persistence: run identity, step boundaries around side effects, and idempotency-aware design are all buildable and load-bearing *without* a durable backend. Only "record progress persistently" and "resume after crash" genuinely require persistence — those are what we're deferring. Approval-specific checklist items are moot since approvals are already out of scope (Part 1).
- **"The control plane decided what run exists" — what does that mean, and is it implemented?** It means: when an event arrives, something must decide whether it belongs to an existing run or starts a new one (the article's own example: a paused run + a user correction forces exactly this decision — resume, append, or fork). That decision belongs to the control plane (Part 3), not the runtime — the runtime only ever executes an already-resolved run. In our project, this resolution isn't implemented, for two reasons: (1) no orchestration/runtime code exists yet, and (2) once it does, the resolution will be trivial (always-new run per turn) because our scope has no interrupted/concurrent runs to disambiguate between — a deliberate simplification, not an oversight.
- **Do we store "runs" the way we store sessions?** No. A stored, resumable run only matters when runs can be interrupted and multiple candidates could exist concurrently — exactly what we deferred. Run identity is a lightweight, in-memory-only ID generated per turn, discarded when the turn completes. This graduates to a real store only if we later add approvals (a run can pause mid-flight) or concurrent runs.
- **Can we still have multiple sessions/conversations?** Yes — "single-session control plane" (Part 3) never meant only one session can exist; `SessionStore.create_session()` already supports many sessions per user (tested). It means there's no automatic *routing* logic that infers which session an ambiguous incoming event belongs to — the caller must already know the `session_id`.
- **Doesn't "the runtime assembles context, calls the model" collapse the model/context-layer boundaries from Parts 2 and 5?** No — the runtime *orchestrates* other layers, it doesn't own their internal logic. It's a conductor, not a performer: it decides *when* in a turn's sequence to call into the model-client module or a future context-assembly module, and what to do with the result (check for tool calls, pause, resume) — but the substance of "how context gets assembled" or "how the model API is called" stays owned by their respective modules (`src/bacteria/model/client.py`, and eventually a `src/context/` module for Part 5).
- **Run vs. runtime vs. workflow, per the article:** "The runtime advances the run. A workflow gives that run a recoverable shape." Three distinct things: a **run** is one unit of work (one execution instance); the **runtime** is the engine that actively advances runs (assembles context, calls the model, invokes tools, pauses/resumes, emits evidence); a **workflow** is not an execution at all but a structural definition — the possible states, isolation boundaries, and wait/continuation rules a run is allowed to have (like a state-machine schema vs. one instance of that machine running).

### Team conclusion

We hold the line on durable execution: **no persistence, no crash-recovery, no resume-after-restart** — a run lives only in-memory for the duration of one turn, same treatment as the Part 3 session store. But we do build the parts of this article that don't require persistence: an explicit `Runtime` module (not a bare inline loop) that owns step-boundary discipline around side effects, extending the retry-safety property we already built into the model client (Part 2) to the run level. Run identity exists but is lightweight and ephemeral, not a stored/resumable entity. The runtime's role is strictly orchestration — it sequences calls into other layers (model client now, context/tools/execution later) without absorbing their internal logic.

### Decisions for this project

- **No durability machinery**: no persisted run store, no replay, no resume-after-crash. In-memory only. → deliberately deferred, same treatment as Part 1/3's durable-execution and approval deferrals.
- **Explicit `Runtime` module**, not a thin inline loop — because step-boundary discipline is genuinely load-bearing (same class of bug as the side-effect-unsafe retries we already guarded against in Part 2). → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **Run identity**: a lightweight ID generated per turn/execution, held in memory only for that run's duration, not persisted. Run resolution ("does this event belong to an existing or new run") stays trivial — always-new — since our scope has no interrupted/concurrent runs to disambiguate between. → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **Step boundaries around side effects**: any tool call gets wrapped so the runtime always knows whether it already executed before deciding a retry is safe — the run-level counterpart to the side-effect-aware retry logic already in `src/bacteria/model/client.py`. → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **Runtime owns sequencing only**: it orchestrates calls into `src/bacteria/model/client.py` (and, later, context/tools/execution modules from Parts 5–7) without owning their internal logic — preserves the ownership boundaries from Parts 1–3 at the orchestration level.
- **Terminology carried forward in code and docs**: retry, replay, resume, and idempotency are kept as distinct concepts even though only retry/idempotency-adjacent logic (step boundaries) is actually implemented now — replay and resume are named as explicitly out of scope, not silently absent.

**Implementation status:** built and tested (5 load-bearing invariant tests in [`tests/test_runtime.py`](../tests/test_runtime.py), all passing) — `Runtime` orchestrates `ModelClient` and `SessionStore` via a per-turn `StepTracker`. Context assembly was a documented stub pending Part 5; retired in favor of a real implementation there.

**Implementation status:** built and tested (5 load-bearing invariant tests in [`tests/test_session_store.py`](../tests/test_session_store.py), all passing) — in-memory only, no persistence backend yet (that's Part 4's territory, durable execution).

---

## Part 5 — Context, Retrieval, and Memory

*Notes: [articles/part-5-context-retrieval-memory.md](../articles/part-5-context-retrieval-memory.md)*

### Discussion

- **"A context layer decides whether accessed evidence should influence the model" — does that decision need to be "intelligent"?** No, not in the AI-judgment sense. The article's own list of what retrieved evidence needs (source, owner, version, freshness, permissions, confidence, provenance) points at deterministic policy checks, not reasoning — does scope match, is it fresh enough, is it permitted. The mechanism can get smarter later (a reranker, an LLM judge), but the architectural requirement is just that *some explicit check* exists instead of trusting a similarity score by default.
- **"So no tools in the context?"** Tool *definitions* are explicitly part of context — the article's own working-set list includes "tool definitions" and "tool outputs." What moves to Part 6 is a different question: not whether the model sees that a tool exists, but whether it's *authorized* to call it, under whose authority, with what limits. Context = visibility; Part 6 = execution authority. Same capability ≠ execution boundary from Part 1, one level deeper.
- **"So then removed?" (re: "durable memory should be an explicit lifecycle event")** Yes — lifecycle explicitly includes expiry/deletion, not just creation. The article's own memory-system question list includes "when should it expire, who can delete it" alongside "what's worth extracting." A memory isn't permanent by default; its removal has to be as deliberate a decision as its creation.
- **"What a source of truth is?"** Recap from Part 1: when a piece of state might exist in more than one place (a store, an in-memory copy, a cache), the source of truth is whichever one is authoritative if they disagree. We already have a concrete instance of this: `SessionStore` is our named source of truth, and `get_state()` returns a deep copy specifically so no caller's local copy can be mistaken for it — mutating the returned copy has zero effect on the store, which is what `test_get_state_returns_a_copy_not_the_authoritative_record` verifies directly.
- **Why does the deep copy matter concretely?** Without it, `get_state()` would return a live reference into the store's internals — any caller mutating it would silently corrupt authoritative state from outside the module that owns it (a classic aliasing bug), and the "only `commit()`/`remember()` mutate state" invariant would only hold by convention, not by construction. The deep copy is what makes the invariant real rather than a comment.
- **Scope for this project:** retrieval (external evidence) deferred — no evidence sources exist yet, same reasoning as deferring durability in Part 4: don't build infrastructure for a need we don't have. Memory: built for real, but in-memory and session-scoped (no persistence backend exists yet, same constraint as Parts 3/4), with explicit writes/removal rather than automatic capture. Context assembly: a bounded recent-message window replacing the `Runtime` stub — not full compaction/summarization, which can wait until actually needed.

### Team conclusion

Context assembly graduates from a stub to a real, owned module (`bacteria.context.assembly`), following the same orchestrator/owner split the runtime already keeps with the model client and session store: `Runtime` decides *when* to assemble context, this module decides *what* belongs in it. The strategy is a hard recent-message window — enough to fix "transcript stuffing" without building compaction machinery we don't need yet. Memory becomes real: a session-scoped, in-memory store of explicitly-written entries, kept structurally separate from both transcript and working-state scratch data, with an explicit removal path (not just writes). Retrieval stays out of scope entirely — there's nothing to retrieve from yet, and building the machinery now would be speculative in exactly the way we've avoided elsewhere in this project.

### Decisions for this project

- **Context assembly is its own module, not Runtime logic.** `Runtime` no longer owns `_transcript_to_messages`; it calls `assemble_context(state, user_text)` and passes the result's `messages`/`system` straight to the model client. → [`src/bacteria/context/assembly.py`](../src/bacteria/context/assembly.py)
- **Bounded recent-window strategy**, not full compaction: the last `window_size` transcript messages, not the whole history — directly fixes failure mode #1 ("transcript stuffing"). → [`src/bacteria/context/assembly.py`](../src/bacteria/context/assembly.py)
- **Memory is surfaced separately from transcript** — formatted into the model request's `system` field, never merged into the message list, so the model-visible shape reflects the real distinction between "what happened" (transcript) and "what the system chose to preserve" (memory).
- **Memory writes are explicit**, through a dedicated `remember()` method — never through `commit()`'s generic working-state path. Each entry carries a `reason` and `created_at`, the article's minimum provenance, even at this small scale. → [`src/bacteria/session/store.py`](../src/bacteria/session/store.py)
- **Memory has an explicit removal path** (`forget()`), not just a write path — lifecycle includes expiry, not only creation. → [`src/bacteria/session/store.py`](../src/bacteria/session/store.py)
- **Retrieval deferred entirely.** No module, no interface stub — same treatment as durable execution in Part 4: named as deliberately out of scope, not overlooked. When a real evidence source exists, it must be treated as candidate evidence, not authority (the article's boundary), when it's eventually built.
- **No persistence yet** — memory and context assembly are both still bound by the in-memory-only constraint from Parts 3/4. Cross-session recall (memory surviving a process restart) isn't achievable until that's revisited.

**Implementation status:** built and tested (6 load-bearing invariant tests: 3 in [`tests/test_context_assembly.py`](../tests/test_context_assembly.py), 2 new in [`tests/test_session_store.py`](../tests/test_session_store.py), all passing — 23/23 across the whole suite). `Runtime`'s Part 4 stub is fully retired.
