"""bacteria — a small agent built as infrastructure rather than as a script.

The whole system is one turn: text arrives, context is assembled, a model is
called, tools may run, state is committed. That loop fits in a single function
(:meth:`bacteria.agent.runtime.runtime.Runtime.run_turn`) and could have been written
as one. It is split into layers instead, because the interesting failures of an
agent are not algorithmic — they are ownership failures. Something wrote state
that should not have. A retry re-ran a side effect. A capability the model could
see became a capability it could use. Each layer here exists to make one of
those impossible by construction rather than by discipline.

Layers, in the order a turn touches them:

- :mod:`bacteria.agent.interfaces` — receives work from outside; owns composition.
- :mod:`bacteria.agent.runtime` — sequences the turn; delegates every step.
- :mod:`bacteria.agent.context` — chooses what the model sees this turn.
- :mod:`bacteria.agent.model` — talks to a provider; proposes, never acts.
- :mod:`bacteria.agent.tools` — describes capabilities, gates them, runs them.
- :mod:`bacteria.agent.session` — the authoritative record; the only writer.

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

**On async.** The layers that touch the outside world are coroutines; the ones
that only compute are not. So :mod:`bacteria.agent.model`, :mod:`bacteria.agent.session`,
:func:`bacteria.agent.tools.execution.execute_tool_call`, and
:meth:`bacteria.agent.runtime.runtime.Runtime.run_turn` are awaited, while
:mod:`bacteria.agent.context`, :mod:`bacteria.agent.tools.registry`, and the error and
output modules are ordinary functions. That split is a readable signal rather
than a style: in this package, ``async def`` means *this reaches outside the
process*. An event loop is started in exactly one place — the console entry
point in :mod:`bacteria.agent.interfaces` — because a library that starts its own
cannot be embedded in a host that already has one.

**This package is self-contained.** The reasoning behind every decision lives in
the docstrings, not in an external document, so the code can be vendored into a
larger project without losing why it is shaped this way. Reading order: this
file, then each subpackage's ``__init__``, then the module you need. Each states
what it owns, what it refuses to do, and — where a plausible simpler approach was
tried and failed — what was rejected and why, so nobody tries it again.

If a ``docs/`` directory travelled alongside, it holds the same decisions in
long form as numbered records. It is supplementary; nothing here depends on it.

**On the gaps.** This system is deliberately incomplete — no persistence, no
retrieval, no isolation, no multi-round tool loop. Those absences are decisions
with recorded reasoning, not unfinished work, and each is documented at the
exact place it would be implemented. To find them all::

    grep -rn "Not built:" src/

Every such block names what is missing, why, and where it would go. The
companion marker is ``Invariant:``, flagging properties that are load-bearing —
those have tests, and breaking one is a bug rather than a design change::

    grep -rn "Invariant:" src/

Keep both accurate when changing things. A ``Not built:`` block describing
something that now exists, or an ``Invariant:`` with no test behind it, is worse
than no marker at all — it is a claim a reader has no reason to doubt.

**On the sparse test suite.** The tests here cover architectural invariants, not
lines. That is deliberate and explained in ``tests/conftest.py``; read it before
concluding the coverage is an oversight, and before adding a coverage gate.
"""
