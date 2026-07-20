# Bacteria — System Design Document

Source of truth for the architecture of the AI agent built in this repository. This document is written incrementally, one article section at a time, from *The Agent Stack* series (https://theagentstack.substack.com/p/the-agent-stack-part-1-a-systems). Each entry below records the team conclusion reached after discussing the corresponding article, not just a summary of the article itself.

See [`articles/`](../articles/) for the raw source notes per part, and [`CLAUDE.md`](../CLAUDE.md) for the working methodology.

---

## Status

| Part | Topic | Status |
|---|---|---|
| 1 | A Systems Map of Modern Agent Infrastructure | Recorded |
| 2 | Infrastructure, Models, and Inference | Recorded |
| 3 | Control Planes, Sessions, and State Ownership | Not started |
| 4 | Runtimes, Workflows, and Durable Execution | Not started |
| 5 | Context, Retrieval, and Memory | Not started |
| 6 | Tools, MCP, and Capability Surfaces | Not started |
| 7 | Execution Surfaces, Identity, and Approval Boundaries | Not started |
| 8 | Observability, Evaluation, and Production Feedback Loops | Not started |

---

## Project Foundations

Cross-cutting decisions that aren't tied to a single article part.

- **Language: Python.** Dominant ecosystem for agent/LLM tooling (LangGraph, most MCP servers, Anthropic/OpenAI SDKs), and the article's own references (LangGraph, Temporal) are Python-friendly. Chosen over TypeScript/Node given our scope doesn't currently need a front-to-back web UI language.

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

- **Model client module:** isolate all direct Anthropic API calls (model asset + interaction contract concerns) behind one module — nothing else in the codebase talks to the API directly. → `src/model/client.py` (planned)
- **No custom serving layer:** rely on the Anthropic API's own handling of queueing/scheduling; our code only needs basic retry/error handling around API calls, not a scheduler.
- **Tool calls treated as proposals, not execution** (per this part's boundary pairs): model output that requests a tool call must pass through explicit application-side authorization before anything runs — carries forward the layer-6/7 capability ≠ execution boundary from Part 1, now reinforced at the model-output level. → ties to `src/tools/` and `src/execution/` (planned, to be detailed in Part 6/7)
- **Structured output treated as untrusted:** any JSON/schema output from the model gets validated by the application, not assumed correct — schema validity is shape, not truth.
- **Caching:** if/when we use prompt caching, name explicitly which cache we mean (provider-side prompt cache vs. any app-level cache we might add later) rather than referring to "the cache" generically.
- **Error handling split by which of the three model-layer components failed**, instead of one generic "API call failed" exception — so retries and logging are correct and diagnosable per the layer that actually broke:
  - *Asset failure* (context window exceeded, unsupported modality, output too long) — not retryable as-is; requires reshaping the request.
  - *Serving failure* (rate limit, timeout, transient 5xx/overload) — retryable, with backoff.
  - *Contract failure* (malformed request, unexpected response shape) — an integration bug, not retryable blindly.
  → `src/model/client.py` (planned) — distinct exception types/handling paths per category.
- **Retry logic must be side-effect-aware:** don't retry a request if a tool call from the prior attempt may have already executed — track whether a side effect occurred before treating a retry as safe. Ties forward to the tools/execution boundary (Part 6/7). → `src/model/client.py` (planned)
- **Structured output validated explicitly**, not trusted on schema-parse success alone (e.g. a pydantic model or equivalent check) before the rest of the app uses it. → `src/model/output.py` (planned)
