# frontend

A browser client for the API in [`../backend/app`](../backend/app). The routes
it consumes are listed in the [API table](../README.md#api); `/docs` on a
running server is the live version.

Vite, TypeScript, and a client generated from the application's own OpenAPI
document. What is here is **Console v0**: signing in, then two tabs — `chat`,
which drives a conversation, and `graph`, which draws memory and its proposals
(with the edges labelled as derived, because ADR 0002 has not built relations
yet). The chain it was built to prove runs underneath all of that and is still
the reason the shape is what it is: the static mount, the session cookie, the
same-origin assumption `SameSite=Strict` rests on, and the generated types —
each verified alone, none of them used together before.

```bash
just console-types   # regenerate the client from the API
just console-build   # build into the package directory the API serves
just console-check   # types, and that the client has not drifted
npm --prefix frontend run dev   # a dev server proxying to :8000
```

`npm run dev` proxies `/auth`, `/chat`, `/ingestion` and `/health` to
`127.0.0.1:8000` rather than pointing the client at a full URL. That keeps
development same-origin, which is the condition the cookie depends on — a CORS
setup here would be a development-only shape production never has.

## The decisions behind it

**A generated client, not a hand-written one.** The application already serves
an OpenAPI document, so the request layer should be generated from it. A
hand-written client duplicates every schema and drifts the first time a field is
added — and the drift shows up as a runtime `undefined` rather than as a build
failure.

`just console-types` dumps the document from `create_app()` — no server, no port,
no database — and `openapi-typescript` turns it into `src/api.gen.ts`, which is
committed. `just console-check` regenerates it and fails when the result differs,
so a renamed response field cannot land without its client change.

**That check runs in CI rather than in a pre-commit hook**, which is a deliberate
departure from what this file used to specify. The hook would need `node_modules`
present to run at all, so it would either fail on a fresh clone or be skipped —
and a hook people skip is worse than a gate that stops the merge. The frontend
job in `.github/workflows/test.yml` is where it actually runs.

It is not only a diff check. Regenerating also type-checks the console against
the new types, which is the half that names the line to change:

```
src/main.ts(87,53): error TS2551: Property 'last_activity_at' does not exist
  on type '{ created_at: string; lastActivityAt: string; session_id: string; }'.
  Did you mean 'lastActivityAt'?
```

**Where the build output goes — decided: served by the API.** The alternative
was a static host or CDN in front of its own build, which keeps the two
deployable independently and costs CORS configuration plus a decision about
where the API URL comes from at build time. It is ruled out by the cookie:
[ADR 0005](../docs/adr/0005-a-browser-holds-a-session-not-a-key.md) makes
`SameSite=Strict` the CSRF answer, and that holds only while the console and the
API share an origin. So the mount and the auth decision are one decision.

The build lands in **`backend/app/src/bacteria/app/console/`**, inside the
package rather than beside the repository, and `create_app` serves it at `/` when
an `index.html` is there. Package data because the alternatives resolve
differently in development and production: a setting cannot be read at that
point at all — `views.py` explains why — and a path relative to the working
directory means one thing for `just serve` at the repository root and another
for a container started elsewhere.

Verified rather than assumed: a wheel built with a file in that directory
contains `bacteria/app/console/index.html`, so `uv_build`'s defaults ship it with
no extra configuration.

The coupling this accepts is the one that shape always had — the backend
distribution now has a directory only the frontend toolchain fills. An unbuilt
checkout is the ordinary case and not an error: nothing is mounted, the API
serves normally, and `/` is a 404.

**An answer for the credential — settled, and it decides the question above.**
This used to read "a browser client cannot hold an API key safely, so this is a
real gap rather than a wiring task". It is now
[ADR 0005](../docs/adr/0005-a-browser-holds-a-session-not-a-key.md): the client
posts a key to `/auth/session` once, and gets back an `HttpOnly` cookie it
cannot read, lasting twelve hours. Nothing in the browser ever holds the key.

**That constrains the build output to the *served by the API* shape.** The
cookie is `SameSite=Strict`, which is what stands in for a CSRF token — and it
only does so while the console and the API share an origin. Putting the console
on a CDN needs CORS *and* a real CSRF token, and would be a decision to record
rather than a configuration change.

Still open here: nothing sweeps expired session rows, and revoking a key does
not end the sessions opened with it.

## No tests here, deliberately, for now

**Nothing in this directory is tested, and that is a decision rather than a
backlog item.** It is recorded here for the same reason ADR 0013 records the
agent's uneven coverage: an absence nobody wrote down reads as an oversight, and
the next person either fixes it without knowing what it cost or leaves it alone
without knowing why.

The console is still moving. Tests written against a screen that is about to be
redrawn assert the layout of a draft, and the cost is paid twice — once writing
them and once deleting them — for a signal that a `tsc` failure would mostly
have given anyway.

What does hold this together meanwhile, so the gap is a known size rather than
an unknown one:

- `just console-check` type-checks the whole console and regenerates the client
  from the API's own OpenAPI document, failing when it differs from what was
  committed. A renamed response field cannot land without the line that reads it
  changing too.
- `just console-build` runs in CI, so a bundle that type-checks but will not
  build fails before the deploy hits it.
- `backend/app/tests/test_console_mount.py` covers the serving: that a mount at
  `/` shadows no API route, that an unbuilt checkout still serves the API, and
  that a half-finished `dist/` is not mistaken for a console.
- `just stack-smoke` builds the image and asserts a console is actually served
  from it, which is the packaging half — the failure that ships silently.

None of which says anything about whether the console *works*. That is the gap,
and it is roughly 800 hand-written lines wide.

**What changes this.** When the front end is definitive — when a screen stops
being redrawn between commits — the tests get written. The useful unit is the
part that is not DOM wiring: what `api.ts` does with errors and expired
sessions, and whatever state and transformation live inside `chat.ts` and
`graph.ts`. If those turn out to be inseparable from the event handlers, then
pulling them out is the first step and the test is what forces it. Adding a test
runner is a dependency, so it is a decision to make then rather than a default
to drift into.

## Running the API without a frontend

```bash
just serve
```

Interactive docs at <http://localhost:8000/docs>, which is enough to exercise
every route by hand.
