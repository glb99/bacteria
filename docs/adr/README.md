# Architecture Decision Records — the application

Decisions about **this workspace and the application** — deployment,
infrastructure, and the shape of the service. Same Nygard format as the agent's:
**Status**, **Context**, **Decision**, **Consequences**.

Separate from [`backend/agent/docs/adr/`](../../backend/agent/docs/adr/), which
numbers its own sequence from 0001. That is not an oversight. The agent is
vendorable — its records travel with it into a host that has never heard of this
application, and a record about FastAPI Cloud would be noise there. When one of
these cites one of those, it says so in full: "the agent's ADR 0017".

The rule for what earns a record is the agent's: a decision that constrains
future work, that a reasonable engineer would make differently, or that is a
deliberate omission which will look like a bug. Library choices and formatting
conventions do not qualify.

| # | Decision | Status |
|---|---|---|
| [0001](0001-run-the-worker-in-the-api-process.md) | Run the job worker inside the API process on single-process platforms | Accepted |
| [0002](0002-the-memory-graph-is-postgres-tables.md) | Build the memory graph as tables in the application's Postgres, not in a graph database | Accepted |
| [0003](0003-observability-is-opentelemetry-exported-to-logfire.md) | Instrument with OpenTelemetry, export to Logfire, and keep both out of the agent | Accepted |
| [0004](0004-authentication-is-shared-authorization-lives-next-to-the-resource.md) | Authenticate once at the edge; decide authorization next to the resource | Accepted |
| [0005](0005-a-browser-holds-a-session-not-a-key.md) | A browser exchanges a key for an expiring, HttpOnly session cookie | Accepted |
| [0006](0006-the-memory-graph-is-an-assertion-log.md) | Build the memory graph as an assertion log with two time axes, in its own feature package | Proposed |
| [0007](0007-the-relation-vocabulary-is-a-catalogue.md) | Govern `rel` with a seeded catalogue, an unratified tail, and derived canonicality | Proposed |
| [0008](0008-preferences-are-assertions.md) | Hold preferences as assertions: a functional relation to a value node, the relation being the memory key | Proposed |
| [0009](0009-the-graph-is-correctable.md) | Give the graph a write surface: retract, rename, link, reject -- as service verbs behind thin routes | Proposed |
| [0010](0010-memory-has-a-port.md) | Give memory a port so the graph can back it, selected by configuration, without replacing the repository | Proposed |
| [0011](0011-a-confirmed-fact-may-be-spoken.md) | Let the owner confirm an extracted fact, making it a retrieval candidate but never a key | Proposed |
| [0012](0012-a-name-is-a-claim-about-a-value.md) | Admit `name` as a functional relation to a value node, replacing the naming denylist | Proposed |
