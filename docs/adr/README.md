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
