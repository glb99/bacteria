# 0005 — A browser holds a session, not a key

## Status

Accepted — 2026-08-19.

Decided before implementation and amended by it. Three things came out of
building it rather than out of arguing about it, and they are the parts most
worth reading:

- **Logout had to prove the secret, not just name the session.** The first
  version revoked on the session id alone. Ids are not secret — this service
  prints them in its own authentication failure logs — so that made logging
  somebody out an unauthenticated write against any id an attacker could read.
- **The prefix separation is a second line, not the mechanism.** Deleting the
  check that a session token cannot parse as a key left every HTTP test green,
  because the two credentials live in two tables and the lookup misses anyway.
  The rule is real but only falsifiable as a unit test, and it is now written as
  one rather than claimed by three docstrings.
- **The tests passed for the wrong reason until the client spoke HTTPS.** httpx
  honours a cookie's `Secure` attribute, so over the default `http://testserver`
  it stored the cookie and never sent it. Every 401 was "no credential
  presented" rather than "credential refused", and three assertions were
  vacuous.

## Context

Console v0 exists as a design and cannot be built, for one reason recorded in
`frontend/README.md` before any of it was drawn:

> Every route except `/health` wants `Authorization: Bearer <key>`, and keys are
> issued by an operator CLI rather than an endpoint […] **A browser client
> cannot hold an API key safely**, so this is a real gap rather than a wiring
> task.

That is right, and the reasons are worth being precise about, because they
determine what the replacement has to be:

- A key in `localStorage` is readable by any script that reaches the page.
- A key in a JavaScript variable is readable by the same script and additionally
  dies on refresh, so the operator pastes it again every time.
- A key never expires ([`keys.py`](../../backend/app/src/bacteria/app/auth/keys.py)
  records "Not built: Expiry" and explains why), so a copy taken once is a copy
  that works until somebody notices and revokes it.
- A key grants everything its principal can do, including — via the same
  credential — being pasted into `bacteria-admin`.

**What already exists and constrains the answer.**

- **Issuance is deliberately not an endpoint.** `auth/service.py`: minting a
  credential over HTTP needs a credential, and the first one has nowhere to come
  from. That argument must survive whatever this record decides.
- **There is no accounts table, by design.**
  [ADR 0004](0004-authentication-is-shared-authorization-lives-next-to-the-resource.md)
  records it, and `keys.py` notes that its SHA-256 would be the wrong hash for a
  password if one ever existed.
- **`auth/` had exactly one way in**, and one 401 for every way of failing. That
  indistinguishability is the property most easily lost by adding a second path.
- **There is one user.** The deployment serves a single principal today.

## Decision

**A browser exchanges a key it already holds for a session cookie.**
`POST /auth/session` takes a key in the body, verifies it through the *same*
`principal_for_key` every route depends on, and returns a `Set-Cookie` marked
`HttpOnly; Secure; SameSite=Strict; Path=/`. `DELETE /auth/session` ends it.

**This does not reopen the issuance argument, and the distinction is the whole
decision.** The endpoint mints nothing from nothing: it takes a credential the
caller has already proven and hands back one that is strictly weaker — twelve
hours, revocable on its own, and unable to issue anything. Compromising it gets
an attacker exactly what presenting the key they already had would have got
them. The bootstrap still happens at `bacteria-admin issue-key`, on a machine
with database access.

**The token is never in a response body.** It exists only in the `Set-Cookie`
header, so no script on the page can read it. Returning the same value as JSON
would undo the entire mechanism while leaving every other part working.

**A session is a separate table, not columns on `api_key`.** They differ in the
column that matters: a key is valid until revoked, a session until it expires.
One table would need a nullable `expires_at` plus a rule, enforceable nowhere,
that key rows must not have one and session rows must.

**Sessions expire; keys do not.** That asymmetry is deliberate rather than an
inconsistency with `keys.py`. Automatic expiry with no rotation story locks
people out — which is why keys have none — and the reasoning inverts here,
because ending a session costs one paste to undo. Twelve hours, as a constant
rather than a setting, on ADR 0004's rule about scopes: a knob nobody has needed
is a knob nobody has tested.

**`SameSite=Strict` is the CSRF answer, and it is an answer with a boundary.**
Every route behind this cookie either reads someone's conversation or writes
their memory, and none should happen because a link was followed. Strict costs
nothing an operator console misses. **This holds only while the console is
served from the same origin as the API** — the "served by the API" option in
`frontend/README.md`. Moving the console to its own origin needs CORS *and* a
real CSRF token, and that is a different record.

**The bearer header is tried first.** A request carrying a key behaves exactly
as it did before sessions existed. Presenting both is not an error and resolves
to the key: there is no case where a caller means "ignore my header", and
refusing the combination would break a console tab open beside a terminal.

**Logging out proves the secret.** Not because logout needs authorization —
it deliberately does not sit behind `CurrentPrincipal`, since requiring a *live*
session to end one would refuse exactly the person whose session went wrong —
but because revoking on an id alone is an unauthenticated write against a value
this service prints in its logs.

## Consequences

**`auth/` now has two ways in, and one 401 to cover both.** Every new failure
mode — expired session, revoked session, wrong secret, cookie that is not a
session token — has to answer identically, and there are now roughly twice as
many chances to get that wrong. Nothing enforces it; it is a rule held by
`UNAUTHENTICATED` being a single object and by the reviewer noticing.

**A session outlives revocation of the key that opened it**, by up to twelve
hours. `principal_id` is copied onto the session rather than joined, for the
reason `ApiKey` separates `principal_id` from `key_id`: revoking a key must not
orphan what it created. The cost is that "revoke this key" is not "log out
everywhere", and there is no command that is. A `bacteria-admin revoke-sessions
<principal>` is the obvious missing verb and is not built.

**Nothing expires the rows.** A session row lives forever after it stops working,
accumulating one per login. That is the same shape as `api_key`, which has
thirty-one rows on a development machine — tolerable, and it will need a sweep
before it is interesting.

**The console must be served from the API's origin.** This record chooses one of
the two shapes `frontend/README.md` left open, without saying so anywhere the
build can check. A future contributor deploying the console to a CDN gets a
console that silently cannot authenticate.

**One more table, one more migration, two more routes**, in a package that had
none.

### The one to dislike

**This is a login system for one user, and it is the second credential type in a
service that could have kept having one.** The alternative it beat — serving the
console from `bacteria-admin` on localhost, where the trust boundary is the
machine and no browser auth is needed at all — is smaller by a table, two routes,
a migration, a cookie policy, and this record. It also reuses an argument this
codebase has already accepted, that reaching the database is a higher bar than
any credential.

It loses on the chat tab, and only on the chat tab. A local console can only run
a turn the way `bacteria-admin chat` does: in-process, against whatever database
it is pointed at. Pointed at production that means the turn runs under a laptop's
provider configuration while the deployed worker picks up its jobs under the
deployment's — one conversation, two configurations, and no way afterwards to
tell which half produced what.

So the honest version is that half of Console v0 justifies this and half of it
did not need it. If the chat tab is ever dropped, this record should be revisited
rather than kept out of momentum.

## Alternatives rejected

**A stateless signed cookie.** No table and no migration: sign
`principal_id + expiry` with a server secret and verify it on the way back. It
loses revocation — a signed cookie is valid until it expires, so logging out is
a client-side gesture and a stolen cookie cannot be killed. This codebase
already has a verb for "make this credential stop working now", and having it
work for one credential and not the other is worse than a table.

**Serving the console locally from `bacteria-admin`.** See above; the strongest
rejected option, and rejected on one tab.

**Real accounts, with passwords or OIDC.** The right answer if a third party
ever gets access, and it reopens ADR 0004's "no accounts table" to serve one
user. `keys.py` would additionally need a real password hash, which it says
itself. Revisit when there is a second person, not before.

**Scoping the session to less than the key grants.** Tempting — a browser
credential that cannot, say, delete memory. It is the scopes question ADR 0004
deferred, and inventing a scope here would settle it as a side effect of a
different decision. The session is exactly as powerful as the key it came from,
which is at least a rule that can be stated in one sentence.

**A refresh token, or sliding expiry.** A session that renews while a tab is
open is not really expiring, and the thing it saves is one paste of a key the
operator already has in a password manager.
