# 0009 — Use local tools instead of MCP

## Status

Accepted — 2026-08-06

## Context

Two things are easy to conflate. A **tool** is the general concept: an entry in
the model's capability surface, described by a schema, callable by name,
regardless of how it is wired up. **MCP** is one protocol for exposing
capabilities across a client–server boundary — JSON-RPC, with a standard
vocabulary for resources, tools, prompts, and sampling. It is a discovery and
transport standard, not a fourth kind of tool, and explicitly not a security
boundary; the specification says so itself.

MCP earns its cost when integrating a growing or third-party set of external
systems and wanting standardized discovery across them.

This system has a fixed set of first-party Python functions, one local user, and
no third-party integrations. Adopting MCP would add a transport, a trust surface
(subprocess launch for stdio, origin validation for HTTP), and a protocol version
to track — in exchange for interoperability nothing here needs.

## Decision

Every tool is a local Python callable this application owns, registered directly
with `ToolRegistry`. No MCP client, no MCP server.

If MCP is adopted later, the role is **client**: this system is the one that
wants capabilities, not the one exposing them. Being a server would mean
publishing this agent's capabilities for other hosts to consume, which is not a
goal anywhere in this project.

Structure the registry so that adoption stays additive. An MCP client would
become an alternative source of `ToolDefinition` objects feeding `register()`;
approval and execution would not change.

## Consequences

The tool path is short and fully debuggable. A failing tool is a Python stack
trace, not a protocol trace across a process boundary.

No third-party MCP server can be used, so any capability someone else has
already built has to be reimplemented locally or the decision revisited. This is
the concrete cost and it grows with the appetite for integrations.

The reversal is bounded because the registry is the only thing that would change.
That is worth verifying rather than trusting: the claim is that
`ToolDefinition`'s four fields can be populated from an MCP tool listing, which
holds for name, description, and input schema, with the handler becoming an RPC
call.

Choosing local tools sidesteps MCP's trust surface without addressing isolation
at all — a local handler runs in-process with full privileges, which is a larger
exposure than a well-configured remote server. See [ADR
0007](0007-tool-calls-are-proposals.md).
