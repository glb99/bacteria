# The Agent Stack — Part 6: Tools, MCP, and Capability Surfaces

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-6-tools-mcp
- **Published:** 2026-05-04
- **Fetched into this repo:** 2026-08-02

## Thesis

A tool is not just a function call. "The model asks. The system acts." Between those two sentences sits everything that matters operationally: which tools are even visible this turn, under whose identity a call executes, what scope it's limited to, whether it needs approval, and where it actually runs. A tool schema validates the *shape* of a request; it says nothing about whether the request should be allowed.

## Key definition: capability surface

**Capability surface** — "the set of actions and context sources the runtime exposes to the model as possible next moves." Not just the tool's name/description/schema/result format — also the runtime's live decision to expose *this* tool, to *this* model, in *this* run, for *this* user, at *this* point in the workflow. The surface changes turn to turn; it isn't a fixed manifest.

## The three layers a schema can't cover

1. **Authorization** — permission questions at the resource level: who can do what, against which resource.
2. **Approval** — a point-of-risk intervention for irreversible or sensitive actions: should this specific action happen *now*.
3. **Execution** — where and how the capability actually runs once permitted.

A schema only constrains argument shape. All three of the above are separate, downstream decisions the schema cannot make for you.

## Boundary pairs

- **Schema ≠ permission.** Clean JSON-RPC structure is not authority.
- **Hosted vs. local vs. connector tools** — different operating responsibility. Hosted: execution shifts to the provider. Local: your application owns credentials and isolation. Connectors: bind to an external service under user authentication (OAuth-style).
- **Resource ≠ Tool ≠ Prompt** (MCP's own primitives) — MCP deliberately keeps these separate rather than collapsing everything into one capability bucket.
- **Connector scope ≠ action approval.** OAuth grants an *access envelope* — what could be done. Approval decides what *should* be done, action by action. Connecting an email account for summarization is not standing permission to send on the user's behalf.
- **Transport changes the boundary.** A stdio MCP server (launches a local subprocess) has different security requirements than an HTTP MCP server (needs origin validation, localhost binding, authentication).

## What MCP standardizes — and what it doesn't

MCP standardizes *capability exchange* over JSON-RPC, with structured primitives: **Resources** (context/data), **Prompts** (templated workflows), **Tools** (executable functions), **Roots** (filesystem boundaries), **Sampling** (server-initiated model calls), **Elicitation** (server-initiated requests for user info).

What it explicitly does **not** do: "It does not replace the runtime. It does not replace authorization. It does not replace approval. It does not decide which execution surface should be trusted." The spec itself warns that tool behavior metadata should not be trusted unless it comes from a trusted server.

**Host responsibility** (the article's term for whatever wires MCP in): creating/managing clients, controlling connection permissions, enforcing security policy and consent, handling user authorization decisions, coordinating model integration, aggregating context across clients. MCP gives you a protocol for capability exchange, not a policy engine.

## Tool output is context, not truth

"Tool output is context with provenance, not truth by default." A tool result enters the runtime with unknown freshness, scope, and trustworthiness — same treatment retrieved evidence got in Part 5. It needs validation (source, freshness, scope) before it's allowed to influence a decision, and doubly so if the tool call touched an external or attacker-influenced surface.

## Named failure modes

1. **Schema treated as permission** — relaxing security because the request parsed cleanly.
2. **MCP treated as a security boundary** — assuming standardization implies trusted servers, safe metadata, correct OAuth, or sandboxed execution. None of that is guaranteed by the protocol.
3. **Tool output treated as truth** — appending results to context without checking source/freshness/scope; stale or attacker-authored content quietly steers the model.
4. **Tool metadata treated as trusted instruction** — names/descriptions/annotations are inputs from whoever wrote the tool, not neutral system facts, if the server isn't trusted.
5. **Connector consent treated as action approval** — access envelope mistaken for a green light to act.
6. **Open-ended tools exposed too early** — shell access, arbitrary URL fetch, unrestricted browser control create huge action spaces (OWASP: prefer granular, intention-revealing tools).
7. **Approval hidden inside tool implementation** — buried approval logic is invisible to audit; no clean record of what paused, what was approved, what should be logged.

## Builder checklist from the article

1. Filter tools per run — expose only what this user/tenant/workflow-stage/task actually needs.
2. Keep tools narrow and intention-revealing (`create_reply_draft`, `search_customer_contracts`) over open-ended (`send_email`, `read_any_drive_file`).
3. Separate schema (shape validation) from authority (policy + downstream authorization).
4. Bind identity explicitly — track whether a call executes as the user, a service account, a connector identity, a local process, or provider infrastructure.
5. Separate connector scope from action approval — sensitive actions may need approval even within an already-granted OAuth envelope.
6. Treat tool output as untrusted context until validated — track source, freshness, scope, external-vs-internal origin.
7. Trace the whole path: what was exposed → what the model selected → what arguments it produced → what policy decided → what was approved → what executed → what came back.
8. Design the next boundary now — once capabilities can change the world, execution surface / identity / approval become first-class architecture (Part 7).

## Why this hands off to Part 7

Context (Part 5) determines what the model can *reason over*. Tools (this part) determine what the model can *ask the system to do*. Neither one determines whether the request actually becomes a real action — that's execution surfaces, identity binding, and approval boundaries, which Part 7 covers directly: "where requests become real actions touching browsers, APIs, databases, code runners, filesystems, devices, or workers."

## Series roadmap

Part 7 next: Execution Surfaces, Identity, and Approval Boundaries.
