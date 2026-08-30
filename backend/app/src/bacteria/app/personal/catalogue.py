"""Which relationships a person's graph has agreed to be about.

``rel`` shipped as a free-text field and the first fortnight of real use produced
ten distinct names across fifteen rows -- ``parent``, ``mother``, ``mother_of``,
``called``, ``name``, ``alternative_name`` and ``interlocutor`` among them,
several of them one fact wearing different hats. None of the three constraints
that existed matched any of them, so the layer that finds contradictions had
never run outside its own tests.

The argument for closing a vocabulary was already made against ``_KINDS``: an
open set means the same thing arrives under three names across three runs and
becomes three things. It was applied to ``kind`` and not to ``rel``, which got a
line of prompt asking the model to be consistent with runs it cannot see.

**This is not a closed enum, and ADR 0007 says why at length.** ``kind`` is five
members describing what sorts of thing exist; ``rel`` is the long tail of a
personal life, and there is no number at which such an enum is finished. A claim
using a relation that is not here is written to the log like any other, because
the tail is the evidence for what this should become and dropping it would
discard exactly the information needed to decide.

**Declared here rather than in the substrate**, which is the change dialogue 14
made and the second domain had already demonstrated: these words are a personal
life's, and :mod:`bacteria.app.graph.catalogue` holds the shape a vocabulary has
and the doctrine by which one grows. ``architecture/catalogue.py`` says the same
thing from the other side -- *the meta-model is borrowed, the entries are not*.

The tail stays a substrate concern for the same reason: *propose on the third
sighting* is a rule about how any discovered vocabulary may change, and it
governs this one rather than belonging to it.
"""

from bacteria.app.graph.catalogue import Alias, Relation, Vocabulary

CATALOGUE: tuple[Relation, ...] = (
    Relation(
        name="employer",
        invariant="A person has one employer at a time.",
        sentence="<src> works for <dst>",
        src_kind="person",
        dst_kind="organization",
        functional=True,
        aliases=(
            Alias("works_for"),
            Alias("employed_by"),
            Alias("employs", converse=True),
        ),
    ),
    Relation(
        name="cto",
        invariant="An organization has one CTO at a time.",
        sentence="<dst> is the CTO of <src>",
        src_kind="organization",
        dst_kind="person",
        functional=True,
        aliases=(Alias("chief_technology_officer"),),
    ),
    Relation(
        name="ceo",
        invariant="An organization has one CEO at a time.",
        sentence="<dst> is the CEO of <src>",
        src_kind="organization",
        dst_kind="person",
        functional=True,
        aliases=(Alias("chief_executive_officer"),),
    ),
    Relation(
        name="mother",
        invariant="A person has one mother.",
        sentence="<src>'s mother is <dst>",
        src_kind="person",
        dst_kind="person",
        functional=True,
        aliases=(Alias("mother_of", converse=True),),
    ),
    Relation(
        name="father",
        invariant="A person has one father.",
        sentence="<src>'s father is <dst>",
        src_kind="person",
        dst_kind="person",
        functional=True,
        aliases=(Alias("father_of", converse=True),),
    ),
    Relation(
        name="tone",
        invariant="A person prefers one tone at a time.",
        sentence="<src> prefers <dst> answers",
        src_kind="person",
        dst_kind="value",
        functional=True,
        aliases=(Alias("prefers_tone"), Alias("style")),
    ),
    Relation(
        name="language",
        invariant="A person is written to in one language at a time.",
        sentence="<src> is written to in <dst>",
        src_kind="person",
        dst_kind="value",
        functional=True,
        aliases=(Alias("speaks"), Alias("prefers_language")),
    ),
    Relation(
        name="name",
        invariant="A person goes by one name at a time.",
        sentence="<src> is called <dst>",
        src_kind="person",
        dst_kind="value",
        functional=True,
        aliases=(
            Alias("user_name"),
            Alias("named"),
            Alias("called"),
            Alias("goes_by"),
            Alias("known_as"),
            Alias("also_known_as"),
            Alias("alternative_name"),
            Alias("alias"),
            Alias("nickname"),
            Alias("first_name"),
            Alias("last_name"),
            Alias("full_name"),
        ),
    ),
    Relation(
        name="same_as",
        sentence="<src> and <dst> are the same thing",
        src_kind=None,
        dst_kind=None,
        functional=False,
        extractable=False,
    ),
    Relation(
        name="lives_in",
        invariant="A person lives in one place at a time.",
        sentence="<src> lives in <dst>",
        src_kind="person",
        dst_kind="place",
        functional=True,
        aliases=(Alias("resides_in"), Alias("lives_at")),
    ),
)
"""The relations that are canonical, which is a seeded six.

**Admitted on one test: can anything check it?** Every entry is functional, so
every entry can produce a contradiction on the day it is used; four also carry an
asymmetric signature that catches an inversion. A relation nothing can check does
nothing here that the tail would not do, while costing a line of prompt.

**Frequency is deliberately not the criterion**, and the observed rows show why.
The most common relation real use produced was ``parent`` — and it is excluded,
because a person has two parents and so nothing can check it. The less common
``mother`` is in.

``cto`` and ``ceo`` are inherited from the three constraints this replaced rather
than re-earned. They are corporate, they appeared in **zero** real rows, and they
stay because removing them is a separate decision from governing the field.

``tone`` and ``language`` are the first entries that point at a *value* rather
than a thing, and they are what makes a preference representable at all. Their
names are the memory keys: one slot per key and one ``dst`` per ``(src, rel)`` at
a time are the same statement, which is why a preference needs no keying
mechanism of its own.

Everything else starts as tail — ``owns``, ``pet``, ``parent``, ``knows`` — and is
promoted by the rule of three once it recurs, which is a change to this literal.
"""


NAME_RELATION = "name"
"""The relation whose object is what to call its subject.

Named rather than spelled at each call site because two things branch on it —
:func:`~bacteria.app.graph.service.confirm`, which redraws the node, and anything
later that wants the owner's name without walking the log — and a string literal
in both is a rename waiting to diverge.
"""


VOCABULARY = Vocabulary(relations=CATALOGUE, names=NAME_RELATION)
"""This domain's words, in the form the substrate accepts.

Handed to :class:`~bacteria.app.graph.repository.SqlGraphRepository` at
construction rather than imported by the service layer, so that a read of the
personal partition is judged by these relations and a read of another partition
is not judged by them at all. Before this existed, every read of every ontology
was measured against a personal life's vocabulary because that was the only one
the substrate could see.
"""
