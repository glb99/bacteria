# Bacteria — System Design Document

Source of truth for the architecture of the AI agent built in this repository. This document is written incrementally, one article section at a time, from *The Agent Stack* series (https://theagentstack.substack.com/p/the-agent-stack-part-1-a-systems). Each entry below records the team conclusion reached after discussing the corresponding article, not just a summary of the article itself.

See [`articles/`](../articles/) for the raw source notes per part, and [`CLAUDE.md`](../CLAUDE.md) for the working methodology.

---

## Status

| Part | Topic | Status |
|---|---|---|
| 1 | A Systems Map of Modern Agent Infrastructure | Recorded |
| 2 | Infrastructure, Models, and Inference | Not started |
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
