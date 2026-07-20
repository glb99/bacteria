# The Agent Stack — Part 2: Foundation Infrastructure, Models, and Inference

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-2-foundation
- **Published:** 2026-04-06
- **Fetched into this repo:** 2026-07-19

## Thesis

The stack starts lower than most agent writing starts: in infrastructure semantics, not agent behavior. Before a single token is processed, the system has already inherited delivery guarantees — where work runs, how it's scheduled, what survives a retry — and those choices constrain everything built on top (retries, streaming, concurrency).

## Splitting "the model layer" into three

What's usually called one thing ("the model") is really three components with different failure modes:

1. **Model asset** — weights, tokenizer, modality support, context window, max output, capability envelope. What the model *can* do in principle.
2. **Serving system** — queueing, schedulers, cache policy, real-world latency profile. How the asset is actually delivered under load.
3. **Interaction contract** — the specific API shape (OpenAI Responses API, Anthropic's tool separation, Gemini variants). How you talk to it.

Same asset behind different serving systems or contracts can behave very differently — conflating the three misattributes failures (e.g. blaming "the model" for what's actually a serving/queueing problem).

## Boundaries that matter (this part's version)

| Not the same as | |
|---|---|
| Context window | Memory — a context window is a *working set* for this request, not persistent state across sessions |
| Tool call (model output) | Execution — tool calls are *proposals*; the application decides authorization and whether to actually run them |
| Structured output validity | Truth / policy compliance — schema-valid output is a *shape guarantee*, not a correctness guarantee |
| API-compatible | Semantically equivalent — a compatible API shape doesn't guarantee equivalent behavior under load |

## Stress-test framing

A single request that includes a long PDF, one tool call, and a requirement for strict JSON output exercises all three model-layer components at once: model asset (token budget), serving system (prefill cost, cache pressure), interaction contract (how the document is packaged, streaming behavior). Useful as a design gut-check.

## Failure modes named

- Using fire-and-forget transport for workflows that need to be durable.
- Conflating long context with memory.
- Treating structured output as authoritative/trusted.
- Mistaking API compatibility for system equivalence.
- Treating all caching (prompt cache, KV cache, app-level cache, etc.) as one undifferentiated thing.

## Builder checklist from the article

- Document delivery and consistency assumptions explicitly.
- Separate model choice, serving choice, and API-contract choice as three distinct decisions.
- Benchmark real request shapes, not toy prompts.
- Treat tool calls and structured outputs as untrusted input from the application's point of view.
- Be specific about which caching layer you mean when you say "cache."
- Carry context, latency, and cost budgets upward into higher layers rather than re-deriving them per layer.
- Distinguish "compatible" from "equivalent."

## Series roadmap (unchanged from Part 1)

Part 3 next: Control Planes, Sessions, and State Ownership.
