# Documentation

One tree, four depths. Start at the question you actually have; each answer is
one hop from here.

## Route by question

| Question | Go to |
|---|---|
| What does this do, and how do I run it? | [`README.md`](../README.md) |
| What routes are there? | [`api.md`](api.md) |
| What works today, and what is missing? | [`status.md`](status.md) |
| How does a request move through it? | [`architecture/README.md`](architecture/README.md) |
| How does the memory graph work, conceptually? | [`architecture/memory-graph.md`](architecture/memory-graph.md) |
| How is the agent layered? | [`../backend/agent/docs/ARCHITECTURE.md`](../backend/agent/docs/ARCHITECTURE.md) |
| Why is it this way? | [`adr/`](adr/README.md) — the application's records |
| Why is the *agent* that way? | [`../backend/agent/docs/adr/`](../backend/agent/docs/adr/README.md) |
| What has broken before? | [`guides/traps.md`](guides/traps.md) |
| How do I know it actually works? | [`guides/verification.md`](guides/verification.md) |
| Why is the code shaped this way? | [`guides/conventions.md`](guides/conventions.md) |
| What are the commands? | [`guides/development.md`](guides/development.md) |
| How do I write a test here? | [`guides/testing.md`](guides/testing.md) |
| How do I write a docstring here? | [`guides/documentation.md`](guides/documentation.md) |
| How do I deploy it? | [`guides/deployment.md`](guides/deployment.md) |
| How did the structure get here? | [`guides/migration.md`](guides/migration.md) |
| Where did the memory design come from? | [`research/`](research/README.md) |
| What is `bacteria-core`? | [`guides/the-origin-repository.md`](guides/the-origin-repository.md) |

## What a thing does

Not in here. It is in the docstring. See
[`guides/documentation.md`](guides/documentation.md) for why that boundary is
held, and for the PEP 257 shape every docstring follows.

## The one split in this tree

`backend/agent/docs/` is **not** part of this directory, on purpose. The agent
package is vendorable — its records travel with it into a host that has never
heard of this application, and a record about FastAPI Cloud would be noise
there. [`adr/README.md`](adr/README.md) states the rule for citing across the
line: in full, as "the agent's ADR 0017".

Everything else lives here.
