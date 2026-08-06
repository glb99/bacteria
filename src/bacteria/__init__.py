"""bacteria — a small agent built as infrastructure rather than as a script.

The whole system is one turn: text arrives, context is assembled, a model is
called, tools may run, state is committed. That loop fits in a single function
(:meth:`bacteria.runtime.runtime.Runtime.run_turn`) and could have been written
as one. It is split into layers instead, because the interesting failures of an
agent are not algorithmic — they are ownership failures. Something wrote state
that should not have. A retry re-ran a side effect. A capability the model could
see became a capability it could use. Each layer here exists to make one of
those impossible by construction rather than by discipline.

Layers, in the order a turn touches them:

- :mod:`bacteria.interfaces` — receives work from outside; owns composition.
- :mod:`bacteria.runtime` — sequences the turn; delegates every step.
- :mod:`bacteria.context` — chooses what the model sees this turn.
- :mod:`bacteria.model` — talks to a provider; proposes, never acts.
- :mod:`bacteria.tools` — describes capabilities, gates them, runs them.
- :mod:`bacteria.session` — the authoritative record; the only writer.

The boundaries worth not collapsing, each a real distinction and each easy to
lose:

- **session ≠ authorization** — "this conversation exists" is bookkeeping;
  "this action is permitted" is a security decision, re-asked every time.
- **transcript ≠ context** — everything that happened, versus the bounded
  subset chosen for one request.
- **memory ≠ history** — a fact deliberately kept, versus a turn that occurred.
- **capability ≠ authority** — the model seeing a tool is not the model being
  allowed to use it.
- **approval ≠ isolation** — "should this run" and "how bad is it if it goes
  wrong" are answered by different mechanisms, and only the first exists here.
- **trace ≠ audit** — how the system reached a result, versus who is answerable
  for it.

Reading order for someone new: this file, then ``docs/ARCHITECTURE.md`` for the
request path and the ownership map, then ``docs/adr/`` for why any particular
thing is the way it is.

**On the gaps.** This system is deliberately incomplete — no persistence, no
retrieval, no isolation, no multi-round tool loop. Those absences are decisions
with recorded reasoning, not unfinished work, and each is documented at the
exact place it would be implemented. To find them all::

    grep -rn "Not built:" src/

Every such block names what is missing, why, and where it would go. The
companion marker is ``Invariant:``, flagging properties that are load-bearing —
those have tests, and breaking one is a bug rather than a design change::

    grep -rn "Invariant:" src/
"""
