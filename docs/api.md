# API reference

Every route the service exposes. Interactive docs are at `/docs` while the
server runs, generated from the same code; this page is the annotated version.

Every route except `/health` and `/auth/session` requires a credential. Anything
wrong with it — missing, malformed, unknown, wrong secret, revoked, expired —
returns the same `401`, because telling them apart tells an attacker which half
of a guess was right.

Two credentials are accepted. `Authorization: Bearer <key>` is the operator's,
issued by CLI and never expiring. A browser instead trades that key once for an
`HttpOnly` cookie that lasts twelve hours and can be revoked on its own, because
a page cannot hold a key safely —
[ADR 0005](adr/0005-a-browser-holds-a-session-not-a-key.md).

| | | |
|---|---|---|
| `GET` | `/health` | Liveness. Does not touch the database, so a database outage cannot cause a restart loop. |
| `POST` | `/auth/session` | `{"key": "..."}` → a session cookie. The only other route that answers without a credential, because it is the one that establishes one. |
| `DELETE` | `/auth/session` | Ends the session server-side and clears the cookie. `204` whether or not there was one. |
| `GET` | `/chat/sessions` | The caller's conversations, most recently active first. The only session route whose ownership is a filter rather than a check, so it takes no `user_id` and never will. |
| `POST` | `/chat/sessions` | Open a conversation. Takes no body — the owner is the authenticated caller and cannot be named by the client. |
| `POST` | `/chat/sessions/{id}/turns` | `{"text": "..."}` → `{"run_id", "reply"}`. Runs one agent turn. |
| `GET` | `/chat/sessions/{id}/transcript` | Everything that happened in the conversation, in order. |
| `GET` | `/chat/sessions/{id}/memory` | What this session is told to remember, with the reason each was kept. |
| `GET` | `/chat/sessions/{id}/extraction` | How far memory extraction has read this conversation, and how far behind it is. A watermark that stops while the transcript grows is a worker that is not running. |
| `PUT` | `/chat/sessions/{id}/memory/{key}` | `{"value", "reason"}`. Preserved into the system prompt of every later turn. Overwrites by key. |
| `DELETE` | `/chat/sessions/{id}/memory/{key}` | `204`, whether or not it was there. |
| `GET` | `/chat/sessions/{id}/memory-proposals` | Suggested memories awaiting a decision. These reach no model. |
| `POST` | `/chat/sessions/{id}/memory-proposals/{source}/{key}` | Accept a suggestion, making it active. `404` if there is no such proposal. |
| `DELETE` | `/chat/sessions/{id}/memory-proposals/{source}/{key}` | Discard a suggestion. `204`. |

### The graph — the personal ontology

What the extractor believes about the person it is talking to, and the write
surface for correcting it. Nothing here edits history: a correction records a new
belief and closes the old one — [ADR 0009](adr/0009-the-graph-is-correctable.md).

| | | |
|---|---|---|
| `GET` | `/graph` | The caller's own graph as it currently stands. |
| `GET` | `/graph/conclusions` | Beliefs the system drew, including the ones that have gone stale. |
| `POST` | `/graph/assertions/{id}/retract` | Stop believing a claim. |
| `POST` | `/graph/assertions/{id}/confirm` | Endorse a claim the extractor proposed, so a prompt may be told it — [ADR 0011](adr/0011-a-confirmed-fact-may-be-spoken.md). |
| `POST` | `/graph/conclusions/{id}/reject` | Withdraw an inferred belief the owner disagrees with. |
| `POST` | `/graph/nodes/{id}/rename` | Correct what a node is called — [ADR 0012](adr/0012-a-name-is-a-claim-about-a-value.md). |
| `POST` | `/graph/links` | Say two nodes are the same thing. Refuses a mismatch of kinds. |

### Architecture — the codebase's ontology

The same assertion log, a different ontology, and the opposite trust model: a
deterministic parse proposes, and a person accepts each proposal. No model is
involved in deriving any of it.

| | | |
|---|---|---|
| `POST` | `/architecture/projects` | Point the service at a checkout. |
| `GET` | `/architecture/projects` | The projects it has been pointed at. |
| `GET` | `/architecture/projects/{id}/model` | The codebase as it stands on disk right now, judged against its rules. Reparsed per request rather than stored — a proposal kept from last week would be arguing about a codebase that no longer exists. |
| `POST` | `/architecture/projects/{id}/classifications` | Agree or disagree with something the codebase suggested about itself. |
| `POST` | `/architecture/projects/{id}/probes/tests` | Run the project's own test command and report what happened. |
| `POST` | `/architecture/projects/{id}/ask` | Ask a model about this codebase, with the codebase in front of it. The one route here that reaches a model. |
| `POST` | `/architecture/projects/{id}/renames` | Say that a package the parse no longer finds is one it does, renamed. |
| `POST` | `/architecture/projects/{id}/order` | Say that one layer sits above another. |

### Ingestion

| | | |
|---|---|---|
| `POST` | `/ingestion/batches` | `{"source", "records": [...]}` → what happened to every record. Runs inline; capped at 500 records. |
| `POST` | `/ingestion/batches:defer` | Same body → `202 {"job_id"}`. Hands it to a worker and answers immediately. |

A session that does not exist and one belonging to someone else both return
`404`. A `403` would confirm the session exists, which turns a session id into
an oracle for enumeration.

### Ingestion in one example

```json
POST /ingestion/batches
{"source": "salesforce-nightly",
 "records": [{"external_id": "c-1", "name": "Ada Lovelace", "seats": 12},
             {"name": "no id"}]}
```

```json
201
{"batch_id": 1, "accepted": 1,
 "rejected": [{"index": 1,
               "payload": {"name": "no id"},
               "reason": "missing required field(s): external_id"}]}
```

A record needs an `external_id` and a `name`; every other key is stored exactly
as it arrived and never inspected, so this fits contacts, products, devices, or
documents equally and knows about none of them. Nothing is dropped silently —
every record becomes either a row or a stored rejection carrying its position in
the submission, the reason, and the payload as it was sent. The index is what
makes two identical bad records distinguishable — the same reason Elasticsearch's
bulk API and SQS's partial batch response report position or id.
