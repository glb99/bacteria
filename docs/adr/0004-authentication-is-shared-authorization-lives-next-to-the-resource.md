# 0004 — Authenticate once at the edge; decide authorization next to the resource

## Status

Accepted — 2026-08-19.

Written after the code rather than before it, and the delay is itself part of the
record: the split existed as a sentence in `CLAUDE.md` and as two modules that
happened to be separate, with nothing saying why a later contributor should keep
them that way. The immediate prompt was `principal_is_known` — a function added
to `auth/` that answers a question about a principal, does **not** answer an
access question, and is one careless call site away from being used as though it
did.

Two things were checked while writing this rather than asserted. Every route does
carry the authentication dependency, and a test now enumerates them from the
OpenAPI schema to say so — the previous hand-written list had drifted to seven of
eleven. And ingestion has no ownership at all; see the consequences.

## Context

The service authenticates with bearer API keys and has exactly one kind of owned
resource: a chat session, with its transcript, its memory, and its proposals.

Before ownership existed, the hole was total. `test_personal_access.py` records it:

> before it, any caller could name any `user_id` and read any session id they
> could guess

Closing that raised the question this record answers, because there are two
plausible places to put the answer and the difference does not show up until the
second feature.

**What the codebase already commits to.**

- **The agent has no notion of a principal.** `chat_session.user_id` is
  deliberately not a foreign key: "the agent's notion of a user is *whoever owns
  this session*, and binding it to an accounts table would make the agent's
  storage depend on a feature it knows nothing about." The same holds for
  `user_memory.user_id`. So ownership is a string comparison the *application*
  makes, over a column with no referential integrity behind it.
- **There is no accounts table.** A principal id is whatever an operator typed at
  `bacteria-admin issue-key`. Nothing validates it, and nothing can.
- **Features own their tables, tasks, and routes**, and `core/` holds nothing
  that names a domain concept.
- **Key issuance is not an endpoint.** The first key cannot be authorized by a
  key, so issuance is an operator command whose access bar is reaching the
  database.
- **Revocation is a timestamp, not a delete**, so that "this key was valid until
  Tuesday" stays answerable.

## Decision

**`auth/` answers exactly one question: who is calling.** It verifies a bearer
token, resolves it to a `Principal`, and stops. `Principal` is frozen — "a
request's identity is established once, at the edge, and nothing downstream may
adjust it" — and its `label` is explicitly never used for access decisions,
because two principals may share one.

**Whether a caller may have a resource is decided beside that resource**, by the
feature that owns it. For sessions that is `chat/access.py`, whose module
docstring states the rule and the reason: only `chat` knows what owning a session
means, and "merging them would put an access decision in a module with no idea
what it is deciding about."

**Every route that touches a session goes through one function.**
`load_owned_session` loads and checks together, so the two cannot come apart.
"One function is something a reviewer can check; an ownership comparison repeated
in each handler is one that will eventually be wrong in one of them."

**Not-yours and does-not-exist give the same answer: 404.** A 403 confirms the
session exists, which turns a session id into an oracle — someone enumerating ids
learns which are real without ever reading one. The distinction is kept in the
log rather than in the response.

**A function in `auth/` that is not an authorization check says so in its first
line.** `principal_is_known` exists for the operator CLI, where a principal is
*typed* rather than proven, and its docstring opens "**Not an authorization
check, and must not be used as one.**" This is a naming rule with teeth: `auth/`
may hold questions about identities, and any such function is one plausible
mis-call away from being a vulnerability.

**Authentication coverage is enforced by a test; authorization coverage is not.**
`test_every_route_refuses_an_unauthenticated_request` enumerates the OpenAPI
schema and asserts 401 on every path but `/health`, with the exemption as a named
constant so that adding one is a visible decision. There is no equivalent for
ownership, and there cannot be a generic one while each feature defines owning
for itself. See the consequences.

**The CLI does not check ownership, deliberately.** `bacteria-admin chat` can
resume anyone's session. Running it requires the database, "which is already more
access than any ownership rule protects against"; the HTTP check exists because a
request arrives from someone who has only a bearer token.

## Consequences

**Every feature that grows an owned resource must write its own check, and
forgetting is silent.** The failure is not an error — it is a caller reading
someone else's data, on a route that works. Nothing in the build says a route
returning a resource skipped the ownership step, and no test can be written for
"the check a feature has not defined yet."

**Ingestion has no ownership, and the code says so in passing.** A batch is
authenticated but not owned: `ingestion/views.py` notes it is not "owned by the
principal that submitted it, so any authenticated caller" can reach it. That is
this record's rule producing a real gap rather than a hypothetical one — the
feature that has not decided what owning a batch means has, by default, decided
that nobody owns one. Acceptable while every principal is trusted and the
deployment has one user. It is the first thing to fix if that stops being true,
and it is not fixed here because inventing an ownership rule for batches is a
decision for whoever needs one.

**There are no roles, scopes, or permissions.** A key cannot be read-only, cannot
be scoped to one session, and cannot be an admin. Every principal may do
everything to what it owns and nothing to anything else. Adding scopes later
means a column, a migration, and a decision about what a key issued before that
column means.

**Two paths reach a session under different rules**, and only one of them is
tested for ownership. Anyone reasoning about who can read a transcript has to
know both.

**`principal_is_known` will be misused eventually.** It returns a bool about a
principal, from `auth/`, and it is one autocomplete away from a route that reads
as authorized and is not. The docstring is the only guard. A stronger shape —
returning something that cannot be mistaken for permission — was not built.

### The one to dislike

**One feature owns resources, so the boundary is being paid for before it is
earned.** Every owned resource in this application is owned by a plain `user_id`
column holding a principal id, which means a single
`require_owner(resource, principal)` in `core/` would work today, in about ten
lines, with one place to review instead of one per feature.

The argument against it is that it would be right until the first resource whose
ownership is not a column — a session shared with a team, a batch owned by an
organization, a memory readable by anyone but writable by its author — at which
point the generic helper either grows special cases for features `core/` must not
name, or gets bypassed by the feature that outgrew it, leaving two mechanisms.
That is a real cost deferred against a real cost paid now, and this record picks
the one that fails by duplication rather than by a wrong central answer. It is
the choice a reasonable engineer most plausibly makes the other way.

## Alternatives rejected

**A central `authorize()` in `auth/`.** The natural shape, and the one this
record exists to refuse. It requires `auth/` to know what a session is, what a
batch is, and what owning each means — putting a decision in a module that cannot
see what it is deciding about, and making the one place every feature's rules
collect the place nobody wants to touch.

**A policy engine (oso, Casbin, or a rules table).** Buys expressiveness this
service has no use for: there is one resource type, one relationship, and no
roles. It would also move the rule out of Python and into a policy file, so "can
this caller read this transcript" stops being answerable by reading
`chat/access.py`.

**Scopes or roles on the API key.** Deferred rather than rejected on principle.
There is no second kind of caller yet, so every scope would be invented rather
than observed, and a scope nobody has needed is a constraint nobody has tested.
The `Principal` object is the place to add one.

**A foreign key from `chat_session.user_id` to an accounts table.** Would make a
mistyped principal impossible, which is the exact failure `principal_is_known`
exists to catch less reliably. Rejected because the table would have to be
visible to the agent's schema, which is the coupling
[the agent's ADR 0021](../../backend/agent/docs/adr/0021-memory-is-scoped-to-a-session-or-a-user.md)
declined for user-scoped memory and for the same reason: the agent must not
depend on a feature it knows nothing about.

**403 for "not yours".** More honest to a legitimate caller who mistyped, and it
tells an illegitimate one which ids exist. The log keeps the distinction for the
only reader who should have it.
