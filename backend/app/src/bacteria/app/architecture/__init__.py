"""An ontology of this codebase, derived from its source rather than reported.

Two layers, and the split is the point:

- :mod:`~bacteria.app.architecture.derive` reads the syntax. Exact, complete,
  re-derivable in a second, and therefore **never written to the assertion
  log** -- storing it would be a cache pretending to be a memory.
- :mod:`~bacteria.app.architecture.checks` holds what people *stated* about the
  arrangement. Small, contestable, and the only part worth keeping.

The proportion is the finding. Ninety-one modules and two hundred and thirty-one
imports are derived; eight boundaries are stated. About five per cent of this
ontology is memory and the rest is a parse -- which is the opposite of the
personal graph next door, where nothing can be recomputed and every row is
testimony.

It shares a substrate with that graph and almost none of its policy. There is no
trust tier here because nobody reported anything, no confirmation step because
nothing was guessed, and no valid time because git already has it. Which of the
graph package's abstractions survive contact with a domain that has no "I" and
no contested claims is a question this package answers by being written.

Not built:
    Any write path. Accepting a crossing, retiring a boundary and recording who
    did either are the stated layer, and they need somewhere to write. Until
    then a boundary is clean or crossed and cannot be argued with, which is the
    single largest thing missing.
"""
