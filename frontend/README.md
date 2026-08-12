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

**A decision about where the build output goes.** Two shapes, and they are not
interchangeable:

- *Served by the API* — the build lands in a directory the ASGI app mounts. One
  origin, no CORS, one thing to deploy. Costs a coupling: the backend image then
  cannot be built without the frontend toolchain.
- *Served separately* — a static host or CDN in front of its own build. Keeps
  the two deployable independently, and requires CORS configuration and a
  decision about where the API URL comes from at build time.

Nothing in the backend currently assumes either. `create_app` in
[`bacteria/app/views.py`](../backend/app/src/bacteria/app/views.py) mounts
routers and a health check and nothing else.

**An answer for the credential.** Every route except `/health` wants
`Authorization: Bearer <key>`, and keys are issued by an operator CLI rather
than an endpoint — deliberately, because minting a credential over HTTP needs a
credential. There is no login, no session cookie, and no browser-facing auth
flow of any kind. **A browser client cannot hold an API key safely**, so this is
a real gap rather than a wiring task: it needs an interactive auth story on the
backend first. See the Status table in the [README](../README.md#status).

## Running the API without a frontend

```bash
just serve
```

Interactive docs at <http://localhost:8000/docs>, which is enough to exercise
every route by hand.
