# bacteria — Project Instructions

## What this is

An AI agent, built from scratch, whose architecture is derived from *The Agent Stack* series by Vinoth Govindarajan (https://theagentstack.substack.com/p/the-agent-stack-part-1-a-systems). The series is the source of truth for the design; this repo is the implementation.

## Working methodology

We go through the series **one part at a time**, in order. For each part:

1. **Fetch and archive** the article into [`articles/`](articles/) as `part-N-slug.md` — a faithful, condensed set of notes (thesis, key structure, definitions, checklists), not a full reproduction of the text.
2. **Explain** the article's content in chat before jumping to implementation — what it argues, why it matters, how it connects to prior parts.
3. **Discuss as a team.** Don't unilaterally decide how the article's ideas apply to this project. Ask what the user thinks, surface tradeoffs, propose an interpretation, and let the conclusion be reached jointly. As the discussion happens (including follow-up questions the user asks about the article), keep a running "Discussion" recap for that part in `docs/SYSTEM_DESIGN.md` — update it incrementally after each meaningful Q&A exchange, not just once at the end. Each entry should capture the question and the settled answer/conclusion, not a verbatim transcript.
4. **Record the conclusion** in [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) under that part's section: the accumulated "Discussion" recap from step 3, the "Team conclusion," and concrete "Decisions for this project" (what we will actually build, and why, not just what the article said). When a decision implies a concrete code artifact, note the intended location inline under that bullet (e.g. `→ src/session/store.ts (planned)`).
5. Only after the design conclusion is recorded do we write or scaffold code for that part, if the part calls for it. When that code lands, update the corresponding decision bullet's inline note from "planned" to the actual path, so the design doc stays a live map from article concept → decision → implementation instead of drifting from the codebase.
6. Update the status table at the top of `docs/SYSTEM_DESIGN.md` as parts move from not started → in discussion → recorded.

Do not skip ahead to later parts before the current part's conclusion is recorded, unless the user explicitly asks to jump around.

## Repo layout

- `articles/` — condensed notes per article part, one file each, cited with source URL and fetch date.
- `docs/SYSTEM_DESIGN.md` — the living system design document. This is the actual deliverable of the discussion process; keep it professional and terse, not a transcript.
- (implementation directories to be added as the design calls for them, once we're past enough of the series to know what we're building)
