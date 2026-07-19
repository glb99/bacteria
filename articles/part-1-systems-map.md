# The Agent Stack — Part 1: A Systems Map of Modern Agent Infrastructure

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-1-a-systems
- **Published:** 2026-03-30
- **Fetched into this repo:** 2026-07-17

## Thesis

"Agent" is too overloaded to be a useful unit of analysis. The useful unit is the *stack* around the model — a request path, wrapped by trust and operator layers, with approvals where side effects become real, sitting on shared infrastructure.

## The ten layers (v1)

1. Interfaces and channels
2. Control plane and session ownership
3. Runtime, workflows, and durable execution
4. Model engine and inference
5. Context, retrieval, and memory
6. Tools, MCP, and capability surfaces
7. Execution surfaces
8. Identity, trust, policy, and approvals
9. Observability, evaluation, and feedback loops
10. Infrastructure substrate

The list isn't the main idea — **ownership** is. For any given layer: which layer owns the run, the working set, callable capability, the side effect, the evidence afterward?

## Request path (event → action)

Interface receives event → control plane resolves session/run/policy → runtime orchestrates (context assembly, model calls, tool calls, approvals, retries, resumption) → model turns prepared input into output/tool-call intent → tools/MCP expose *what may be asked for* → execution surfaces perform *what actually happens* → observability/evaluation capture evidence and judge quality afterward.

## Boundaries that matter (collapse these and things get "haunted")

| Not the same as | |
|---|---|
| Session | Authorization |
| Transcript | Context |
| Memory | Learning (weight updates) |
| Capability (tool schema) | Execution (side effect + blast radius) |
| Approval (should it proceed) | Isolation (what it can do once it proceeds) |
| Observability (evidence) | Evaluation (judgment) |

## Builder checklist from the article

- Name the source of truth for session ownership.
- Decide what belongs on the hot path vs. background flows.
- Separate transcript, context, and memory in code and language.
- Separate capability exposure from execution authority.
- Put approvals where side effects become real.
- Trace runs, then evaluate them with explicit criteria.
- Choose durable execution based on retry/wait/resume needs, not demo convenience.

## Series roadmap

1. A Systems Map of Modern Agent Infrastructure (this article)
2. Infrastructure, Models, and Inference
3. Control Planes, Sessions, and State Ownership
4. Runtimes, Workflows, and Durable Execution
5. Context, Retrieval, and Memory
6. Tools, MCP, and Capability Surfaces
7. Execution Surfaces, Identity, and Approval Boundaries
8. Observability, Evaluation, and Production Feedback Loops
