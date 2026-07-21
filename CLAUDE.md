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

Reading ahead in the *source articles* yourself, for personal awareness, is fine and encouraged (light skim, not a close read) — it helps you spot cross-layer dependencies early. That is separate from the team formally discussing/designing/recording a part, which must still happen strictly in order.

## Implementation timing

Build code **interleaved, part by part** — implement a part's planned artifact right after its design conclusion is recorded, not after all 8 parts are designed. Reasons: untested design assumptions compound silently across later parts if left on paper too long, and a module only really validates a decision once it's actually run. This applies even though later parts sometimes contain knowledge relevant to an earlier part's implementation (e.g. Part 8's observability concerns touching Part 2's error handling):

- If implementing a part needs a hook into a later, undiscussed layer, build the **smallest possible stub** and flag it explicitly as provisional (e.g. a comment or doc note: "minimal stub, revisit in Part N"). Do not fully design that later layer early just to support the stub.

## Testing approach

Not every design decision needs an automated test. Split "Decisions for this project" bullets into two kinds:

- **Load-bearing invariants** — a claim about behavior that, if silently violated, causes a real bug or incident (e.g. "a retry must never re-execute a tool call that already ran," "the model never writes directly to the session store"). These get a real, automated test that fails when the invariant is broken. This is the same idea as an "architectural fitness function" (Ford/Parsons/Kua, *Building Evolutionary Architectures*): an executable, repeatable check that preserves an architectural characteristic over time.
- **Rationale/preference decisions** — a judgment call about *why* we built something a certain way, with no runtime behavior to assert (e.g. "we chose Anthropic direct over a provider abstraction because it was premature abstraction"). These stay as documentation in `docs/SYSTEM_DESIGN.md` only — do not write a test for them.

Keep the number of tests per part small and deliberate (a handful of genuinely load-bearing boundaries, not one test per decision bullet) — the point is targeted verification of what would actually hurt if it broke, not exhaustive coverage of every design nuance. When verifying a module, also prefer a real end-to-end run over isolated unit tests alone, and specifically try to reproduce any failure modes named in that part's article (e.g. Part 3's six named failure modes) rather than only testing the happy path.

## Repo layout

- `articles/` — condensed notes per article part, one file each, cited with source URL and fetch date.
- `docs/SYSTEM_DESIGN.md` — the living system design document. This is the actual deliverable of the discussion process; keep it professional and terse, not a transcript.
- (implementation directories to be added as the design calls for them, once we're past enough of the series to know what we're building)
