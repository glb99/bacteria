# 0002 — Build the memory graph as tables in the application's Postgres, not in a graph database

## Status

Accepted — 2026-08-14

Accepted after phase one shipped rather than before, which is the order this
particular bet deserved. The record's central claim is that the extractor is the
half worth having, and that was testable: run live, it first renamed one fact on
every pass — `name`, `first_name`, `preferred_name`, `nickname` — which would
have become four node identities for one person had the graph been built on it
first. Showing it the keys already in use, split into confirmed and
merely-suggested, settled it: three consecutive runs over the same transcript
proposed one fact under the confirmed key.

Phase two — nodes, edges, vectors, traversal — remains unbuilt and is the part
still taken on faith. The Consequences below are unchanged by acceptance,
including the one to dislike.

Depends on the agent's ADR 0024, which decides the shape this reaches the agent
in and stays Proposed until something implements it. This record decides where
the data lives and what writes it.

## Context

Memory today is a keyed preference store: `chat_memory_entry`,
`chat_user_memory_entry` and `chat_memory_proposal`, each row a `value`, a
`reason`, a `source` and a timestamp. Selection is recency. There is no graph in
it and no corpus to build one from — except the transcript, which is stored
complete and append-only in `chat_transcript_item`, and of which only the last
twenty messages ever reach a model.

That asymmetry is the opportunity. The database holds every turn of every
conversation; the model has only ever seen a sliding window of it. Anything that
reads the whole record knows things no turn could.

The agent's ADR 0017 expected two proposers. One exists: the `remember` tool,
registered per turn in `chat/service.py`, which proposes with `source="model"`
and cannot write active memory. The other — "a background job over the
transcript, built by the host" — was never built. There is an `ingestion/tasks.py`
and no `chat/tasks.py`. Nothing in this application has ever read a stored
transcript for anything.

So "add GraphRAG" is really two things: build the missing proposer, and give
retrieval an index to query. The question of *which database* is the smaller
half, and it is the half with a clear answer.

### What this repository has already committed to

Six constraints, each already written down and most already paid for. They are
what eliminate the candidates, and they do it before any benchmark is consulted.

- **A job is enqueued inside the transaction that justifies it.** That is the
  entire reason the queue is Postgres and not Redis (`core/jobs.py`, and
  [ADR 0001](0001-run-the-worker-in-the-api-process.md)). A store outside that
  transaction reopens the window this system is organised against — on every
  memory write, not on an edge case.
- **Migrations own the schema**, and a drift test replays them and asserts no
  diff against the models. A store whose schema is created by a client library on
  first write sits outside that guarantee.
- **The deployment target runs one process.** The worker is already folded into
  the API because there is nowhere else to put it. Postgres arrives through the
  Neon or Supabase integration. A second server is a second thing to host on a
  platform that hosts one.
- **The agent has no database.** Storage is reached only through protocols it
  declares. A library that couples retrieval to a driver cannot live in
  `bacteria.agent` at all.
- **Nothing the model produced reaches a later prompt unconfirmed** (the agent's
  ADRs 0016 and 0017).
- **Every test runs on real Postgres**, one throwaway database per run, truncated
  between tests, no SQLite anywhere. A second store needs its own fixture and its
  own answer for what happens when it is not running.

### What was evaluated

**Apache AGE** — openCypher inside Postgres, Apache-2.0, supporting PG 11 through
18. On the merits it is the best fit in the field: one database, one transaction,
one backup, a real query language. It is eliminated by hosting rather than by
design. It is not offered by Neon and not offered by Supabase, whose Nix-built
images cannot compile extensions at runtime — and those two are exactly what
`docs/guides/deployment.md` tells someone to attach. Choosing AGE means choosing to
run Postgres ourselves, which is a larger decision than this one.

**Neo4j, Memgraph, FalkorDB, Amazon Neptune** — separate servers, and all four
fail the transaction constraint identically. Licensing is a secondary objection
and worth noting anyway beside this repository's Apache-2.0: Neo4j Community is
GPLv3, Memgraph is BSL, FalkorDB is SSPLv1, which is source-available rather than
open source.

**Kuzu** — the embedded answer, which would have avoided the server entirely. Its
repository was archived in October 2025 when its sponsor was acquired; Graphiti
has deprecated its driver as "upstream project unmaintained". It also uses
file-based locking, which the in-API worker would contend with.

**Graphiti** — the best temporal model available for agent memory, and it offers
Neo4j, FalkorDB and Neptune, so it inherits their failure. Its bitemporal edges
are worth taking; its dependency is not.

**Microsoft GraphRAG** — offline hierarchical summarisation with community
detection, re-indexed in batches, reported at $50–200 per 500-page corpus against
roughly $0.50 for LightRAG on the same input. Memory is incremental by
definition; this is the wrong shape at any price.

**LightRAG** — incremental and cheap, and its PostgreSQL graph backend is
AGE-dependent, so it fails where AGE fails. Worth reading rather than adopting.

**Cognee** — the closest peer, Apache-2.0, and it now ships a Postgres graph
backend precisely to avoid this problem, reporting it about 10% faster than the
split graph-plus-vector stack it replaced because retrieval stops crossing a
service boundary. It also brings its own memory model, which is the part this
project has already designed and recorded across eight ADRs.

**Mem0** — not an option, and the most useful data point here. It shipped five
graph-store drivers (Neo4j, Memgraph, Kuzu, Neptune, Apache AGE) and deleted all
of them in April 2026, replacing them with entity linking inside the vector store
it already had.

### What makes plain tables sufficient

The workload is shallow. Agent-memory retrieval is dominated by one-hop work:
find a node, expand its direct edges, rank. A published breakdown of LightRAG's
own graph calls puts around 85% at one hop, with its only breadth-first traversal
bounded to depth 2 and fifty nodes. Recursive CTEs are strong exactly there. They
are weak at variable-depth search, shortest paths and cycle detection, none of
which this workload reaches.

And there is an upgrade path that the extension does not have. SQL/PGQ — the
SQL:2023 property-graph standard, `CREATE PROPERTY GRAPH` and `GRAPH_TABLE` — was
committed to Postgres master on 2026-03-16 and lands in PG 19. It is defined
*over ordinary tables*. A nodes-and-edges schema is what a property graph gets
declared on top of later. An AGE graph is not.

## Decision

**The graph is tables in this application's Postgres, alongside everything else.**
Three of them, owned by `chat/` because features own their tables, each stating
its own key the way the memory tables do.

```
memory_node     (user_id, node_id)             label, kind, attrs, first_seen, last_seen
memory_edge     (user_id, src, rel, dst)       attrs, valid_from, valid_to, session_id, run_id
memory_node_vec (user_id, node_id)             embedding vector(1536)
```

**Keyed by `user_id`, not `session_id`.** This is the one place the graph
deliberately does not mirror the memory tables. Their split exists because which
table a row is in states whether a human decided the fact outlives its
conversation (the agent's ADR 0021). A derived index carries no such decision, so
partitioning it by scope would encode a promotion nobody made. More practically:
a graph's entire value is that an entity mentioned in two conversations becomes
one node, and a session-scoped graph is a set of islands each covering a
conversation whose text the model can already see in its window.

`session_id` and `run_id` stay on edges as **provenance rather than partition** —
which is what makes "where did this edge come from" answerable, and what the
agent's ADR 0018 already bought for transcript items.

**Bitemporal edges from the start.** `valid_from` and `valid_to`, so a fact that
stopped being true is invalidated rather than deleted and "what did this system
believe last Tuesday" stays answerable. Taken from Graphiti, which is the one
idea worth taking from it. It costs a column pair now and is expensive to
retrofit once there are edges.

**Derived, and treated as derived.** Every row is recomputable from the
transcript. It is not backed up separately, a migration may drop and rebuild it,
and a bad extractor is fixed by re-running rather than by a data migration. This
is the property that distinguishes it from `chat_memory_entry`, where deleting a
row loses a human's activation decision that exists nowhere else.

**Extraction is a deferred job, incremental, enqueued in the turn's own
transaction.** A new `chat/tasks.py`, the second proposer the agent's ADR 0017
expected. It reads forward from a `(session_id, seq)` watermark rather than
re-reading the transcript, which keeps its cost proportional to new turns instead
of to conversation length — the difference between incremental indexing and a
full re-index, and the reason the Microsoft GraphRAG numbers above do not apply
to us. It proposes under one fixed `source`, so `(source, key)` keeps a re-run
idempotent.

**The graph never contributes text.** Anything it discovers becomes a
`chat_memory_proposal` a human activates. What it may do is decide which already
activated memories are surfaced, which is the agent's ADR 0024 boundary and is
enforced there by the supplier returning `MemoryEntry` values and nothing else.

**pgvector, via `CREATE EXTENSION vector` in a migration.** Both Neon and
Supabase ship it, so the deployed side needs nothing. `compose.yml` moves from
`postgres:17-alpine` to an image carrying the extension. That extension is the
only new infrastructure in this record.

**Embeddings are 1,536-dimensional, and the number is a constraint rather than a
preference.** pgvector's HNSW and IVFFlat indexes cap at **2,000 dimensions**.
The column type will store up to 16,000, so a larger vector is accepted, written,
and queried perfectly — by sequential scan, forever, because it cannot be
indexed. That failure is invisible at the size a test database reaches and
arrives as unexplained latency at the size a real one does, which is the exact
shape of bug this repository keeps a whole section of `CLAUDE.md` about.

Gemini's `gemini-embedding-001` returns 3,072 by default and supports Matryoshka
truncation to 1,536 or 768, so the bound costs nothing but has to be asked for.
**With that model, truncated vectors need normalizing by hand** — only the newer
one normalizes them itself — and skipping it does not raise, it just makes
similarity quietly wrong. Both facts belong here because both are silent when got
wrong.

`halfvec` indexes above 2,000 and is the escape hatch if 3,072 is ever wanted.

**Embeddings behind `BACTERIA_EMBEDDING_PROVIDER`, defaulting to Gemini.** A
separate setting from `BACTERIA_MODEL_PROVIDER` and not derived from it, because
the embedder genuinely is a different choice from the chat model — Anthropic
publishes no embedding model at all and documents Voyage AI instead. Folding the
two together would make an Anthropic deployment mysteriously require a Gemini
key; a separate setting makes the requirement explicit and refuses to boot
without it, which is the rule the `BACTERIA_` prefix already enforces everywhere
else.

**Built in two phases, and the first one is not the graph.** Phase one is the
extractor and the proposals it writes: `chat/tasks.py`, `chat/extraction.py`, and
a watermark table. It needs no pgvector, no nodes, no edges, and no change to the
agent — proposals go through `SqlSessionRepository.propose`, which already
exists. Phase two is the graph and the retrieval seam the agent's ADR 0024
describes.

The ordering is deliberate and it is the cheap way to be wrong. If the extractor
turns out to propose noise, that is visible after one phase, in a review queue,
having built nothing that depends on it — where the same discovery made after
building traversals and an embedding pipeline would have cost all of it. It also
means everything below about vectors and edges is a commitment on paper before it
is a commitment in code.

## Consequences

The graph shares a transaction with the turn that produced it, a schema with
Alembic, a fixture with every other test, and a backup with everything else.
There is nothing new to operate, and no state that can be up while the rest is
down or the reverse.

**We write the traversals.** No Cypher, no path algebra, no algorithms library.
If the workload ever wants community detection or shortest paths, the answer will
be to pull a subgraph into NetworkX inside a job, and that is a real limitation
rather than a workaround anybody enjoys.

**A recursive CTE is easy to write and easy to write badly.** An unbounded one
over a cyclic graph does not return. Depth caps and a visited set are
load-bearing, and by this repository's rule the guard gets a test that has been
watched failing.

**`just db-up` changes under everyone.** A stock `postgres:17` image no longer
serves, so every clone re-pulls, and the first symptom of getting it wrong is a
migration failing on `CREATE EXTENSION`. This is the first time this project has
required anything of Postgres beyond being Postgres.

**A second vendor for a feature that is not the model.** An Anthropic-only
deployment now needs a Gemini credential before retrieval works at all. That is
two API keys for one feature, and the alternative — Voyage — is a third vendor
rather than a second.

**Every turn gains an extraction call.** Roughly doubling per-turn model spend,
for a feature whose benefit is invisible until proposals accumulate. Making it
deferred keeps it off the request's latency and does not make it free.

**The graph inherits the retention decision nobody has made.** Transcripts are
kept forever, not as a policy but as a default that ADR 0020 declined to settle;
the graph now grows with them. Being derived means it can be rebuilt smaller once
a retention rule exists, which is a mitigation and not an answer.

**The review queue problem becomes acute.** The README already lists "a nudge to
review proposals" as a deliberate gap. An extractor running on every turn
produces proposals continuously, and nothing surfaces how many are waiting — so
the first deployment to ignore the queue concludes the agent has no memory while
it behaves exactly as designed. This record makes that gap urgent without closing
it.

**`payload` is `JSON`, not `JSONB`.** The extractor reads transcript payloads,
and the generic column type gives no GIN index and no containment operator
without a cast. Converting is cheap now and expensive once the table is large,
so it should happen in the same migration or be consciously declined.

### The one to dislike

**This may not earn its keep.** With a few hundred memories per user, a vector
index over confirmed entries plus the existing recency rule would likely retrieve
about as well for a fraction of the machinery, and every consequence above would
be avoided. The graph earns its place when *relations between facts* start
mattering — whose manager, which project a preference belonged to — and nothing
in the current data says that has happened. This record is a bet that it will,
made before the evidence, and the honest version of it is that the extractor and
the proposals are the valuable half while the edges are the speculative one.

## Alternatives rejected

**Apache AGE.** Better on the merits and unavailable on the two Postgres
providers this project's deployment documentation names. Revisit if this ever
runs its own Postgres, at which point the schema here is what would migrate.

**A dedicated graph database** — Neo4j, Memgraph, FalkorDB, Neptune. Each gives
up the enqueue-inside-the-transaction property, adds a process to a
single-process platform, puts a schema outside Alembic, and adds a store the test
suite must reason about being absent. No retrieval benefit at this size
compensates for the first of those.

**Graphiti, or Cognee, or LightRAG.** Adopting a memory framework means adopting
its memory model, and this project's model is the part that is already designed,
recorded and tested across the agent's ADRs 0016, 0017, 0021, 0022 and 0024.
Taking their ideas is free; taking their abstractions would mean re-litigating
decisions that are settled.

**Vectors only, no graph at all.** `memory_node_vec` over confirmed memory
entries, no edges, no extraction of relations. Cheaper, simpler, and plausibly
sufficient — this is the strongest rejected alternative and the one to reach for
first if the extractor turns out to be the valuable half. It is declined here
only because relations between remembered facts are the thing being asked for,
and a vector index cannot represent one.

**Wait for SQL/PGQ in PG 19.** It would give the query language without the
extension. It is not released, this project runs PG 17, and the schema chosen
here is exactly what a property graph would later be declared over — so waiting
buys nothing that building now forecloses.
