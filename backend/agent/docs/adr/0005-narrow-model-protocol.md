# 0005 — Depend on a narrow protocol, not a provider abstraction layer

## Status

Accepted — 2026-08-06

## Context

Building against one vendor's SDK throughout means a swap touches everything.
The usual remedy is a provider abstraction layer: a common interface covering
messages, streaming, tool calling, token accounting, and caching, with an
adapter per vendor.

Written before a second provider exists, that layer is a guess about what
providers have in common. The guess is usually wrong in a specific way — it
generalizes from one SDK's shape, and the second provider then either does not
fit or forces the interface wider. Repeat, and the abstraction becomes a union
of every vendor's surface area, which abstracts nothing.

The opposite failure is worse in a different way: with no seam at all, the
runtime imports a vendor SDK directly and swapping providers means editing
orchestration code.

## Decision

Define the smallest contract the runtime actually requires: one method,
`send(messages, **kwargs) -> ModelResponse`, as a structural `Protocol` in
`model/protocol.py`. Nothing about streaming, token counts, caching, or
batching.

Every caller depends on the protocol; nothing outside `model/` imports a vendor
SDK.

Mark it `@runtime_checkable` so conformance can be asserted in a test, while
being clear about what that check is worth — it verifies the method exists, not
that it behaves.

Validate the seam with a real second implementation rather than asserting it.
`GeminiClient` exists mainly for this reason: a protocol with one implementation
is a claim, and with two it is a tested one.

## Consequences

Providers are genuinely swappable. Adding Gemini required no change to the
runtime, the tool loop, or the session store — that was checked by doing it, not
assumed.

A narrow contract is cheap to honor. A new provider implements one method.

Provider-specific capabilities are unreachable through the protocol. Prompt
caching, streaming, and thinking modes all exist in the underlying SDKs and none
are exposed. Exposing one means either widening the contract for everyone or
adding an optional method the runtime must feature-detect — both deferred until
something needs it.

Structural typing means a mistyped implementation fails at call time rather than
at definition. The `isinstance` check catches a missing method and nothing
subtler; the behavioral tests are what actually protect a new provider.

The protocol makes the *call* swappable. It does not make the payload
provider-neutral — see [ADR
0006](0006-anthropic-block-shapes-as-internal-format.md), which is where the
remaining coupling lives.
