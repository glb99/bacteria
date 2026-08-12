# Security

## Reporting a vulnerability

Report privately through
[GitHub's advisory form](https://github.com/glb99/bacteria/security/advisories/new),
not as a public issue.

Include what you did, what happened, and what you expected. A proof of concept
helps. Expect an acknowledgement within a week.

## What this project is

**This is a study project, not production software.** It is deliberately
incomplete in ways that are documented rather than hidden — see the "Deliberately
absent" table in the [README](README.md) and `grep -rn "Not built:"`. Nothing here
has been through a security review.

## Known limitations, by design

These are recorded here so nobody reports them as findings, and so nobody deploys
this assuming otherwise. Each is documented at the place in the code it would be
fixed.

| Limitation | Where |
|---|---|
| **A registered tool runs in-process with full privileges.** Approval answers "should this happen" and says nothing about "how far does the damage reach". There is no sandbox, no timeout, and no resource limit, so every registered tool must be trusted first-party code. That is the security model, not an oversight. | `bacteria/agent/tools/execution.py` |
| **API keys grant identity and therefore everything.** No scopes, no expiry, no read-only credential to hand a script. A key is valid until explicitly revoked. | `bacteria/app/auth/keys.py` |
| **Ingested records have no tenancy.** Submitting requires authentication, but a batch is not owned by its submitter. This becomes urgent the moment a read route exists. | `bacteria/app/ingestion/views.py` |
| **`database_url` is a plain `str`.** It will carry a password and can be printed, logged, or serialized into an error page by anything holding it. A real deployment wants `SecretStr` and a rule about what may be logged. | `bacteria/app/core/settings.py` |
| **Tool output reaches the model unmarked.** Nothing distinguishes content from an untrusted source, so the current tool set has to stay one where that does not arise. | `bacteria/agent/tools/execution.py` |
| **No retention or redaction rule.** Tool inputs and user text are recorded verbatim in the transcript, which was cheap when state died with the process and is a standing liability now that it is persisted. | `bacteria/agent/session/store.py` |
| **Trace and audit are one record.** Debugging wants broad access, audit wants tight control; splitting them is a host decision nobody has made. | `backend/agent/docs/ARCHITECTURE.md` |

## What is deliberately defended

Also worth stating, because these look like accidents and are not:

- **Every authentication failure returns an identical 401.** Missing, malformed,
  unknown, wrong secret, revoked — all the same to the client. Distinguishing them
  tells an attacker which half of a guess was right. The distinction is kept in
  the log.
- **A session that does not exist and one belonging to someone else both return
  404.** A 403 would confirm the session exists, turning a session id into an
  enumeration oracle.
- **Key secrets are compared with `hmac.compare_digest`,** and only a SHA-256 hash
  is stored. SHA-256 rather than bcrypt/argon2 is deliberate and reasoned about in
  `auth/keys.py` — these are 256-bit random keys, not passwords. That reasoning
  does not transfer to passwords, and this application stores none.
- **The model cannot write active memory.** It can only propose, because memory is
  injected into the system prompt of every later turn — so a model that could
  write it directly could author its own future instructions. See
  [ADR 0017](backend/agent/docs/adr/0017-memory-is-proposed-and-confirmed.md).
- **Credentials are issued by an operator CLI, never an HTTP route.** Minting a
  credential over HTTP needs a credential, and the first one has nowhere to come
  from.
