# Assistant

Use the assistant to understand the system. Writing code is a separate request, made explicitly in the current message.

## Boundaries

- For a request to understand, compare, or decide, read `.grok/skills/research-session/SKILL.md` and follow it before the substantive answer.
- Create or edit source, tests, config, or docs only when the current message explicitly asks for that change.
- Do not create or edit anything under `docs/adr/`. The person writes architecture decision records. Project permission rules deny those edits.
- Files the assistant authors go under `ai/`. The folder contract is `ai/README.md`.

## Continuity

- Read `ai/sessions/index.md` and the overlapping session records before adding a new model of the system.
- Treat a model as shared only after the alignment check in the research-session skill, or after the person waives that check.
- When a later message contradicts a session record, update that record's gaps.
