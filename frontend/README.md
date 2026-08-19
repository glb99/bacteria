# frontend

Nothing here yet. This directory exists so the shape of the repository states
the intent, and so the questions below are answered before code arrives rather
than discovered by it.

## What goes here

A browser client for the API in [`../backend/app`](../backend/app). The routes
it would consume are listed in the [API table](../README.md#api); `/docs` on a
running server is the live version.

## What it will need, and why each is a decision

**A generated client, not a hand-written one.** The application already serves
an OpenAPI document, so the request layer should be generated from it. A
hand-written client duplicates every schema and drifts the first time a field is
added — and the drift shows up as a runtime `undefined` rather than as a build
failure. Whatever generates it belongs in a pre-commit hook, so that a backend
change and its client change land in the same commit.

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

## Running the API without a frontend

```bash
just serve
```

Interactive docs at <http://localhost:8000/docs>, which is enough to exercise
every route by hand.
