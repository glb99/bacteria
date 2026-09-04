# The other bacteria repository

**Two different things are now called bacteria, and the ambiguity is new.** This
repository took the name in the rename that produced `bacteria.agent` and
`bacteria.app`; the repository below had it first. When either is meant, say
which:

- **this one** — the workspace, at `~/Documents/Projects/bacteria`, whose agent
  package is `backend/agent` and imports as `bacteria.agent`.
- **the origin** — `~/Documents/Projects/bacteria-core`, frozen, described below.

This file said the origin was at `~/Projects/bacteria` until that path was
checked and found not to exist. It is `bacteria-core`, in the same directory as
everything else. A third directory, `~/Documents/Projects/bacteria-main`, shares
the prefix and is a different project entirely — not a git repository, and
nothing here depends on it.

`backend/agent` came in via `git subtree` and is the working copy. Every
change to the agent belongs here. The subtree link is not maintained — the
directory has since been renamed and its modules moved under a namespace, so a
future `git subtree pull` would not apply cleanly and should not be attempted.

`bacteria-core` is where it started — the study project it was built in,
working through an article series. It is frozen at `f58e89b`, 2026-08-06, which
is **before the async refactor**: its code is synchronous throughout and has no
`session/protocol.py`. Never copy code from it in this direction.

It is not merely stale, though, and that is the part worth knowing. It holds
`docs/SYSTEM_DESIGN.md` and `docs/sequence.mmd`, which **exist nowhere else** —
the part-by-part design record that the ADRs replaced. So the two diverged in
kind and not only in commits: this copy has `docs/adr/` and no `SYSTEM_DESIGN.md`,
that one has the reverse.

Which means "sync them" is the wrong instinct in both directions. Code flows
neither way; that repository is a frozen origin. If anything in
`SYSTEM_DESIGN.md` still earns its place, move that content deliberately into an
ADR or `ARCHITECTURE.md` — do not reintroduce the article-part framing, which
was retired on purpose.
