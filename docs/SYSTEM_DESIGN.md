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
| 6 | Tools, MCP, and Capability Surfaces | Recorded |
| 7 | Execution Surfaces, Identity, and Approval Boundaries | Recorded |
| 8 | Observability, Evaluation, and Production Feedback Loops | Recorded |

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

---

## Part 6 — Tools, MCP, and Capability Surfaces

*Notes: [articles/part-6-tools-mcp-capability-surfaces.md](../articles/part-6-tools-mcp-capability-surfaces.md)*

### Discussion

- **Does `test_tool_calls_are_surfaced_as_proposals_not_executed` actually test non-execution?** No — caught mid-discussion. It only asserts `result.tool_calls` matches the expected list (a response-shape/passthrough check). The "never executed" claim in its docstring was true, but for a structural reason the test itself doesn't check: `client.py` has no filesystem/subprocess code capable of acting on a tool name. Left as-is deliberately — there was no execution layer yet for a real non-execution invariant to protect. Now that one exists, the real invariant is tested directly by `test_runtime_executes_tool_calls_via_the_execution_module_not_the_model_client`.
- **What's the actual difference between "a tool" and "MCP"?** A tool is the general capability concept — an entry in the model's capability surface, callable via schema, regardless of how it's wired up (hosted / local / connector). MCP is one specific *protocol* for exposing capabilities across a client-server boundary (JSON-RPC; Resources/Tools/Prompts/Roots/Sampling/Elicitation) — a standardized discovery/transport layer, not a fourth kind of tool, and explicitly not a security boundary (the spec itself says so).
- **Given that, which should this project use, and by what criteria?** MCP earns its complexity when integrating a growing or third-party set of external systems and wanting standardized discovery/interop. Local tools are the right call for a small, fixed, project-owned action set with no interop need — same capability-surface boundary from this part, without MCP's own added trust surface (subprocess launch for stdio, origin validation for HTTP). This project currently has zero tools of any kind, one local user, and no third-party integrations — local tools first, same "don't build infrastructure for a need we don't have" call as retrieval (Part 5) and durability (Part 4).
- **If MCP is ever adopted, would it be as a client or a server?** Client/host, not server. Bacteria is the agent — the thing wanting more capabilities — which is the MCP client/host role (connecting out to someone else's server). Being an MCP *server* would mean exposing bacteria's own capabilities for other agent hosts to consume, which isn't a stated goal anywhere in this project.

### Team conclusion

Build the proposal → execution seam for real, scoped to local tools only, with MCP explicitly deferred. A `ToolRegistry` owns the capability surface (what tools exist, what's exposed for a given run); a separate `execution` module is the only place a tool's handler actually runs, kept structurally apart from both the model client (which only ever reports a proposal) and the runtime (which orchestrates *when* execution happens, not how a call is authorized). Authorization and approval are named only as the smallest possible hook (an `approve` callback defaulting to "always allow") — full design of that boundary is explicitly Part 7's job ("Execution Surfaces, Identity, and Approval Boundaries"), not this part's, per `CLAUDE.md`'s minimal-stub-for-later-layers rule.

### Decisions for this project

- **Tools are local only — no MCP client/server.** Revisit when there's a concrete need to consume an existing third-party MCP server (client role); a server role isn't currently justified by anything in this project's goals. → [`src/bacteria/tools/registry.py`](../src/bacteria/tools/registry.py)
- **The model-facing schema never carries the handler.** `ToolDefinition.to_schema()` returns only `name`/`description`/`input_schema` — the callable that would actually run code never reaches the model or crosses into request payloads. → [`src/bacteria/tools/registry.py`](../src/bacteria/tools/registry.py)
- **Per-run filtering exists but isn't yet driven by real policy.** `ToolRegistry.schemas_for_run(allowed=...)` supports exposing a narrowed set (checklist item 1), but nothing yet decides *what* should be allowed per user/workflow — there's only one user and no workflow stages to scope against yet.
- **Execution is a dedicated module, not Runtime logic and not ModelClient logic.** `execute_tool_call()` is the only place a handler runs; it looks up the tool, gates on `approve` (stub, defaults to always-allow), and wraps handler failures rather than leaking them raw. → [`src/bacteria/tools/execution.py`](../src/bacteria/tools/execution.py)
- **Runtime drives exactly one round of tool execution per turn** — call model, execute any proposed tools via the execution module (step-tracked, per Part 4's idempotency discipline), call model once more with results, return. Not a multi-round agentic loop — that's more machinery than anything currently needs. → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **Tool execution is recorded in the transcript** (`TranscriptItem(kind="tool_call", ...)`), not just passed through silently — directly guards failure mode #7 ("approval hidden in implementation"): what ran and what it returned is visible in session state, not buried inside a callback.
- **Authorization/approval get only a stub (`approve`, defaults to always-allow)**, explicitly not designed here — Part 7 owns that boundary. Flagged as provisional, not a security decision to build on. → [`src/bacteria/tools/execution.py`](../src/bacteria/tools/execution.py)

**Implementation status:** built and tested (9 new load-bearing invariant tests: 3 in [`tests/test_tool_registry.py`](../tests/test_tool_registry.py), 4 in [`tests/test_tool_execution.py`](../tests/test_tool_execution.py), 2 in [`tests/test_runtime.py`](../tests/test_runtime.py) — full suite 34/34 at the time). **Update:** a first real tool now exists — `add_note` ([`src/bacteria/tools/notes.py`](../src/bacteria/tools/notes.py)), a small local side effect (appends to a gitignored local notes file), registered and wired into the CLI alongside `cli_approve`. Chosen deliberately small but non-trivial, so the approval boundary gates something real instead of a no-op. See the Layer 1 addendum below for the CLI wiring.

---

## Part 7 — Execution Surfaces, Identity, and Approval Boundaries

*Notes: [articles/part-7-execution-surfaces-identity-approval.md](../articles/part-7-execution-surfaces-identity-approval.md)*

### Discussion

- **How much of this part actually applies at our scale?** Most of the article's texture (OAuth scopes, tenant isolation, browser sessions, service-account credentials, sandboxing infrastructure) assumes production multi-tenant surfaces this project doesn't have — one local user, zero real tools registered, local Python function calls, no external connectors. Same shape of call as deferring retrieval (Part 5) and durability (Part 4): legitimately out of scope for now, not overlooked.
- **Is any of it not speculative?** Yes — the `approve` hook in [`bacteria.tools.execution`](../src/bacteria/tools/execution.py) was already built in Part 6 as an explicit stub pointing at this part. "Should this specific call happen now" is a real, answerable question the moment any tool with a side effect exists, even at single-user scale — unlike identity envelopes or sandboxing, which need a multi-principal or multi-trust-level system to mean anything.
- **Scope for this project:** build the approval boundary only — a real, working `approve` implementation and the plumbing to supply one to `Runtime.run_turn()`. Defer identity envelopes, policy/enforcement separation, sandboxing, and the untrusted-content-authority invariant entirely; they need surfaces (OAuth, multiple trust levels, real side-effecting tools) this project doesn't have yet.

### Team conclusion

Approval is the one control from this part worth making real right now, because the seam for it already exists (Part 6's `approve` stub) and it doesn't require inventing any infrastructure this project doesn't need — everything else in Part 7 (identity envelopes, policy/enforcement/sandboxing as distinct mechanisms, the untrusted-content invariant) stays documented only, revisited once a concrete need shows up (a second identity, a real side-effecting tool, an untrusted content source).

### Decisions for this project

- **A real approval implementation, not just the stub's default.** `cli_approve()` asks the local user directly, describing the pending call (name + arguments) per the article's "good approval text" — placed at the point of the actual side effect (inside `bacteria.tools.execution`), not at task start. → [`src/bacteria/tools/approval.py`](../src/bacteria/tools/approval.py)
- **Approval defaults to denied, not allowed, on ambiguous input.** Anything other than an explicit yes rejects the call — matches the article's framing of approval as a real gate, not a formality.
- **`Runtime.run_turn()` now accepts an `approve` callback**, threaded through to `execute_tool_call()` for every proposed tool call in a turn. Omitting it preserves Part 6's always-allow default, so existing callers (and tests) aren't broken by this addition. → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **Rejection fails the turn loudly** — `ToolExecutionError` propagates out of `run_turn()` rather than being caught and fed back to the model as a soft failure. Simplest correct behavior at this scope; a graceful "the user declined, here's why" round-trip back to the model is a real nicety, deliberately not built until there's an actual interactive user relying on it (the CLI doesn't wire in `tool_registry`/`approve` yet — see Layer 1 addendum below).
- **Identity, policy/enforcement/sandboxing separation, and the untrusted-content-authority invariant are deferred entirely.** No stubs, no placeholders — same treatment retrieval (Part 5) and durability (Part 4) got. Revisit when a concrete need exists: a second identity/principal, a tool with a real external side effect, or a content source that isn't fully trusted.

**Implementation status:** built and tested (7 new load-bearing invariant tests: 3 in [`tests/test_tool_approval.py`](../tests/test_tool_approval.py), 2 approval-specific in [`tests/test_runtime.py`](../tests/test_runtime.py) — full suite 39/39 at the time). **Update:** `cli_approve` is now wired into [`src/bacteria/interfaces/cli.py`](../src/bacteria/interfaces/cli.py) alongside the first real tool (`add_note`, Part 6) — see the Layer 1 addendum below.

---

## Part 8 — Observability, Evaluation, and Production Feedback Loops

*Notes: [articles/part-8-observability-evaluation-feedback-loops.md](../articles/part-8-observability-evaluation-feedback-loops.md)*

### Discussion

- **"What accountability is?"** (re: "an audit trail preserves accountability") — a trace answers *how* the system reached a result (mechanism). An audit trail answers *who is answerable* for it (responsibility): which identity acted, under what granted scope, which policy allowed it, whether approval was required and by whom it was given, what changed. The test: given a bad outcome, can you point to a specific identity/authorization/approval chain, not just a sequence of function calls.
- **"Still evals? or unit tests?"** (re: "write an assertion" instead of asking a model judge) — genuinely blurry by the article's own taxonomy, which names deterministic checks as one of three kinds of evaluation. Mechanically identical to a unit test (same `assert`); the real difference is subject and lifecycle — a unit test checks a function against crafted inputs, pre-release; a deterministic eval checks a whole agent run's recorded behavior, often against real captured traces, as ongoing regression coverage gating each release. Maps directly onto this project's already-adopted "architectural fitness function" testing philosophy (`CLAUDE.md`) — a deterministic eval is a fitness function for agent *behavior* instead of code *architecture*.
- **"Which parts should be automated, is it CI/CD?"** (re: the bad-run → triage → dataset → regression → gate → canary loop) — yes, CI/CD generalized past code correctness into behavioral correctness. Fully automatable: running the regression suite, gating a release on it, canary rollout with auto-rollback. Semi-automatable: flagging candidate bad runs. Inherently human: triaging *why* a run was bad, and the actual fix. The one non-CI/CD-shaped addition is that judgment step at the front, which a normal test pipeline doesn't need because "did this pass" isn't always a clean boolean.
- **Scope for this project:** most of the article assumes a production audience this project doesn't have — release gates, canary rollouts, SLOs, distributional-drift monitoring, a redaction/retention story for traces containing user data. All deferred, same treatment as retrieval (Part 5) and identity/sandboxing (Part 7). But a concrete, non-speculative gap surfaced during discussion: `execute_tool_call` failures (rejection, unknown tool, handler error) currently propagate straight out of `run_turn` *before* `commit()` runs — meaning a failed run leaves zero evidence, not even the user's message. That's the same root cause behind the `CredentialsError` gap found when the CLI was first run for real (Layer 1 addendum, below) — a run-level failure loses everything accumulated so far. This directly violates the article's stated invariant ("every meaningful run should leave enough evidence to explain how the system reached the result... even a failed one") and is worth fixing for real, independent of any production-scale motivation.

### Team conclusion

Build the observability half only, scoped tightly to "don't lose evidence on failure" — nothing about evaluation infrastructure or feedback loops, since there's no eval suite beyond pytest's existing regression coverage and no release process to feed a loop into. Enrich the tool-call transcript record to include what was actually requested (`input`), not just what came back (`output`), and make sure any run-level failure — a rejected/failed tool call, or a failure in the model call itself — still commits whatever evidence was accumulated before re-raising, instead of silently discarding it.

### Decisions for this project

- **Tool-call transcript records now include `input`, not just `output`**, and an explicit `status` (`executed`/`failed`) — matches the article's "the trace crosses the stack" requirement; previously the record of *what was requested* didn't exist at all, only what came back. → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **A failed or rejected tool call is committed as evidence, not silently lost.** `run_turn` catches `ToolExecutionError` around each call, appends a `tool_call` transcript item recording what was attempted and why it failed, then re-raises — the caller still sees the failure loudly (Part 7's decision stands: no soft-recovery round-trip to the model), but the session now has a permanent record of the attempt. → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **Any run-level exception commits accumulated evidence before re-raising**, tagged as a `run_error` transcript item. Closes the same gap the `CredentialsError` discovery exposed for the model call itself — previously a model-call failure lost even the user's message. → [`src/bacteria/runtime/runtime.py`](../src/bacteria/runtime/runtime.py)
- **Trace and audit stay unified, not split into separate records.** The article warns against collapsing them in production because the audiences differ (broad engineering access to debug logs vs. tightly controlled audit access). This project has one developer and no such audience split — deferred as a real distinction to make later if that ever changes, not built now.
- **No evaluation or feedback-loop infrastructure.** No dataset pipeline, no release gate, no online monitoring — nothing in this project ships a "release" in the sense the article means. Pytest's existing suite already plays the role of regression coverage per this project's established testing philosophy (`CLAUDE.md`); that's judged sufficient at this scale, not a placeholder for something bigger.

**Implementation status:** built and tested (3 new/extended load-bearing invariant tests in [`tests/test_runtime.py`](../tests/test_runtime.py) — full suite 41/41). Verified against the real `ModelClient` too, not just fakes: re-running the no-credentials case from the Layer 1 addendum now shows the user's message and a `run_error` record both surviving in the transcript, where previously nothing was committed at all.

---

## Layer 1 — Interfaces and Channels (outside the article's Part sequence)

Part 1's systems map names ten layers, but Parts 2-8 map onto layers 2-9 one-to-one — layer 1 ("interfaces and channels": where work enters the system) never gets its own dedicated part. Following `CLAUDE.md`'s part-by-part ritual strictly would mean this layer never gets built at all, purely because the source material happens not to loop back to it, not because it's actually out of scope. Treated as a cross-cutting addendum instead of a numbered part, prompted by a real gap: nothing in the codebase outside of mocked tests ever constructed a real `ModelClient` or drove `Runtime` end-to-end.

### Decisions for this project

- **A minimal real CLI entry point**, not a design exercise — the smallest thing that receives work from outside (stdin) and hands it to `Runtime.run_turn()`, matching layer 1's one job per Part 1: receive the event, then hand off to the control plane/runtime. → [`src/bacteria/interfaces/cli.py`](../src/bacteria/interfaces/cli.py)
- **Wires the real `ModelClient`** (no fake/mock) together with `SessionStore` and `Runtime`, registered as a console script (`bacteria`) via `[project.scripts]` in `pyproject.toml`.
- **No session/run resolution logic** — one session is created per process invocation. Real resolution (reusing a session across invocations, choosing which session an event belongs to) is exactly the control-plane concern Part 3 already covers structurally; this entry point doesn't need to reinvent it for a single-user local CLI.
- **Owns constructing the tool registry**, for the same reason it owns constructing `ModelClient`/`SessionStore`: nothing else in the project has a notion of "what capabilities does this deployment have." Registers `add_note` (Part 6) and wires `cli_approve` (Part 7) as the real approval boundary — the CLI is where "the model asks, the system decides" actually terminates for this project, since there's no separate control-plane module to own it instead.

**Implementation status:** built, imports cleanly, and was run for real (no `ANTHROPIC_API_KEY` set locally). Running it surfaced a genuine gap rather than a hypothetical one: `ModelClient._classify()` had never been exercised against a real Anthropic SDK exception before. A missing-credentials failure raises a raw `TypeError` from the SDK's auth resolution, before any HTTP call — that didn't match any of `_classify`'s named exception types, so it fell through to the generic `ContractError` catch-all. Fixed: added a fourth error category, `CredentialsError` (see [`src/bacteria/model/errors.py`](../src/bacteria/model/errors.py)), deliberately kept outside Part 2's asset/serving/contract three-way split — those all describe a well-formed *attempt* failing, whereas missing/invalid credentials mean the attempt was never authorized at all. `_classify()` now recognizes both the local pre-flight `TypeError` and the server-rejected `anthropic.AuthenticationError` (401) case, routing both to `CredentialsError` — non-retryable, same as `AssetError`/`ContractError`. Two new load-bearing tests in [`tests/test_model_client.py`](../tests/test_model_client.py) (`test_missing_credentials_is_not_retried`, `test_rejected_credentials_is_not_retried`); full suite now 25/25. **Update:** the CLI now also registers `add_note` and wires `cli_approve`, closing the "no real tool anywhere" gap flagged since Part 6. 4 new load-bearing tests in [`tests/test_tool_notes.py`](../tests/test_tool_notes.py); full suite now 45/45.
