# Assistant notes

These files are working notes from research sessions. They are not project documentation, and the documentation site does not publish this folder.

Architecture decision records live in `docs/adr/` and are written by a person. A session may name an ADR id after that record exists. The session does not create the record.

## What goes here

- `session-template.md` — the report structure for one session.
- `sessions/` — one markdown file per research session, plus the index.

Add another subdirectory only when a session needs an artifact other than its record, and only when asked.

## Session files

Copy `session-template.md` to `sessions/YYYY-MM-DD-short-slug.md`.

`sessions/index.md` lists every session, newest first. The ADR column stays empty until a person has written the record and named its id.

## Status

| Status | Meaning |
| --- | --- |
| `exploring` | The opening interview or the research is still open. |
| `gaps` | The alignment check found a mismatch or an unchecked claim, or the check was skipped. |
| `aligned` | The person confirmed the shared model, including any gaps they accept as still open. |
