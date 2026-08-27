"""Which relationships the graph has agreed to be about.

`rel` shipped as a free-text field and the first fortnight of real use produced
ten distinct names across fifteen rows — `parent`, `mother`, `mother_of`,
`called`, `name`, `alternative_name` and `interlocutor` among them, several of
them one fact wearing different hats. None of the three constraints that existed
matched any of them, so the layer that finds contradictions had never run outside
its own tests.

The argument for closing a vocabulary was already made in this package, against
``_KINDS``: an open set means the same thing arrives under three names across
three runs and becomes three things. It was applied to ``kind`` and not to
``rel``, which got a line of prompt asking the model to be consistent with runs
it cannot see.

**This is not a closed enum, and ADR 0007 says why at length.** ``kind`` is five
members describing what sorts of thing exist; ``rel`` is the long tail of a
personal life, and there is no number at which such an enum is finished. A claim
using a relation that is not here is written to the log like any other — see
:func:`is_canonical` — because the tail is the evidence for what this should
become, and dropping it would discard exactly the information needed to decide.

**Canonicality is derived and never stored.** A relation is canonical iff it is
in here, computed at read time. A column would make promotion an ``UPDATE``
across historical rows, which is an append-only log being mutated; derived,
promotion is an edit to this literal and every past row reclassifies for free.

Not built:
    Anywhere for an entry to come from. This stays a literal for the reason the
    constraints it absorbed already gave: it moves to rows keyed by owner when an
    authoring route exists, since "a person has one employer" is exactly the kind
    of rule a particular person is entitled to disagree with.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Alias:
    """Another word for a relation already in the catalogue.

    ``converse`` is the half that is easy to miss and expensive to get wrong.
    ``mother_of`` is not a synonym of ``mother`` but its opposite: *X is the
    mother of Y* and *X's mother is Y* point in opposite directions, so applying
    the alias has to swap the ends. Without the flag, canonicalizing
    ``self —mother_of→ Guillermo`` would merge a backwards edge into the right
    relation and make it confidently wrong.
    """

    name: str
    converse: bool = False


@dataclass(frozen=True)
class Relation:
    """One relationship the graph knows how to talk about.

    ``sentence`` is not documentation. It goes into the extraction prompt, and it
    is what makes direction **stated rather than requested** — the previous design
    asked the model to "keep the same direction every time" across calls that
    cannot see each other, which is not a thing it can do.

    ``src_kind`` and ``dst_kind`` are a signature, and ``None`` means *any* — used
    by ``same_as``, which relates two things of whatever kind they both are, and
    so has no single pair to state. An asymmetric signature catches
    an inverted claim outright — ``employer (person → organization)`` cannot be
    stated backwards without the kinds disagreeing. A symmetric one catches
    nothing, which is why :attr:`functional` and not the signature is what admits
    a relation here.

    ``functional`` means at most one ``dst`` per ``(user_id, src)`` at any one
    moment, and it is what used to be a ``FunctionalConstraint``. Folding it in
    dissolves an oddity ADR 0006 left behind: evidence is a foreign key to the
    assertion log and a constraint had no row to point at, because a constraint
    was never a thing. It is a property of a relation.

    ``invariant`` states that rule in a sentence, and is **not** the same text as
    :attr:`sentence` even though ADR 0007's sketch had one field doing both. They
    answer different questions: *"<dst> is the CTO of <src>"* says which way round
    to read a claim, and *"An organization has one CTO at a time"* says what
    cannot be true twice. A person shown a contradiction needs the second — the
    rule here is a hypothesis about their world rather than something the system
    is entitled to enforce, so they have to be able to read it and disagree, and
    the reading template gives them nothing to disagree with. It is ``None``
    exactly when :attr:`functional` is false, because then there is no rule.
    """

    name: str
    sentence: str
    src_kind: Optional[str]
    dst_kind: Optional[str]
    functional: bool
    invariant: Optional[str] = None
    aliases: tuple[Alias, ...] = ()
    extractable: bool = True
    """May the extractor propose this relation?

    True for everything a transcript can state. False for the one relation a
    person must assert themselves: ``same_as``, because ADR 0006's asymmetry says
    splitting one thing across two nodes is recoverable and **collapsing two
    things into one is not**. A model proposing merges from the vocabulary it is
    handed would be doing exactly the irreversible thing, one plausible guess at
    a time.

    This is the point where the catalogue stops being one list. It answers two
    questions — *what may be recorded* and *what may be suggested* — and they had
    the same answer until identity arrived.
    """


@dataclass(frozen=True)
class Resolution:
    """A relation name the catalogue recognizes, and what applying it costs.

    ``swap`` is true when the name arrived as a converse alias and the claim's
    ends must be exchanged before it is recorded.
    """

    relation: Relation
    swap: bool


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


def preferences() -> tuple[Relation, ...]:
    """The relations a projection may turn into keyed memory.

    Functional and pointing at a value: the first because a key holds one answer,
    the second because a key holds a *word* rather than a reference to something
    else in the graph. ``mother`` is functional and is not a preference; ``pet``
    points at a thing and is not either.
    """
    return tuple(r for r in CATALOGUE if r.functional and r.dst_kind == "value")


_BY_NAME: dict[str, Relation] = {relation.name: relation for relation in CATALOGUE}

_BY_ALIAS: dict[str, Resolution] = {
    alias.name: Resolution(relation, alias.converse)
    for relation in CATALOGUE
    for alias in relation.aliases
}


def lookup(name: str) -> Optional[Relation]:
    """The catalogue entry for a relation name, or ``None`` if it has none.

    Exact match. Aliases are not consulted, because the callers that need this —
    conflict evaluation, the console's rule list — are asking about a relation as
    it was *recorded*, and an assertion's ``rel`` has already been canonicalized
    by the time it reaches the log.
    """
    return _BY_NAME.get(name)


def is_canonical(name: str) -> bool:
    """Is this relation one the catalogue has agreed to?

    The whole of the derived predicate ADR 0007 decided on. There is no column
    and no cached copy: a relation's status is a fact about the catalogue as it
    stands now, not about the row, and promoting one reclassifies every past
    assertion without touching any of them.
    """
    return name in _BY_NAME


def resolve(name: str) -> Optional[Resolution]:
    """Canonicalize a relation name the model proposed, or ``None`` for the tail.

    Consults the catalogue first and aliases second, so a name that is both is
    read as itself.

    Returning ``None`` is not a rejection. The caller records the claim under the
    model's own word; this only says the catalogue has nothing to say about it.
    """
    relation = _BY_NAME.get(name)
    if relation is not None:
        return Resolution(relation, swap=False)
    return _BY_ALIAS.get(name)


def functional() -> tuple[Relation, ...]:
    """Every relation that can produce a contradiction.

    Which is currently all of them, and the caller must not assume that: the
    admission test says a relation needs *something* able to check it, and an
    asymmetric kind signature qualifies on its own.
    """
    return tuple(relation for relation in CATALOGUE if relation.functional)


def vocabulary() -> str:
    """The catalogue as the extraction prompt states it.

    Rendered rather than written out beside the prompt, so the two cannot
    disagree. ``PROMPT_VERSION`` is a hash of the prompt text and therefore moves
    whenever this does, which is the property retraction wanted and could not
    have while the vocabulary was implicit in whatever the model chose.
    """
    lines = []
    for relation in CATALOGUE:
        # A relation the extractor may not propose is not offered to it. `same_as`
        # is the case: a model suggesting merges would be guessing in the one
        # direction ADR 0006 calls unrecoverable.
        # Converse aliases are deliberately not advertised. They exist to
        # recognize a name a model reaches for unasked, and listing `mother_of`
        # under a sentence reading "<src>'s mother is <dst>" would invite exactly
        # the inversion the flag exists to undo.
        if not relation.extractable:
            continue
        synonyms = ", ".join(alias.name for alias in relation.aliases if not alias.converse)
        suffix = f" (also: {synonyms})" if synonyms else ""
        lines.append(f"  {relation.name} - {relation.sentence}{suffix}")
    return "\n".join(lines)


def read_as(relation: Relation, src: str, dst: str) -> str:
    """One claim as a sentence, from the catalogue's own template.

    Takes labels rather than an assertion, so this module keeps knowing nothing
    about the log — and so the two callers that need it, a conclusion's statement
    and a confirmed fact's, cannot render the same relation differently.

    The first version of the conclusion renderer built statements from node ids
    and produced *"1385501d-… took over cto of dcaad500-…"*: correct, and
    unusable by the person expected to disagree with it.
    """
    return relation.sentence.replace("<src>", src).replace("<dst>", dst)


PROMOTION_THRESHOLD = 3
"""How often a relation must recur before it is worth asking about.

The rule of three, doing here what it does for object types: a shape seen once is
an accident and a shape seen three times is a pattern. It is a threshold for
*asking*, never for acting — nothing promotes a relation but an edit to
:data:`CATALOGUE`.
"""


@dataclass(frozen=True)
class Candidate:
    """A tail relation that has recurred often enough to be worth a look."""

    name: str
    count: int


def promotable(tally: dict[str, int], *, threshold: int = PROMOTION_THRESHOLD) -> list[Candidate]:
    """Which relations outside the catalogue have earned a question.

    Pure, and takes the counts rather than fetching them, so the rule is testable
    without a database and the query is somewhere a query belongs.

    Sorted by how often each was seen, because a reader working down the list
    should meet the strongest case first — and ties by name, so two runs over
    unchanged data print the same thing and a diff means something.
    """
    candidates = [
        Candidate(name, count)
        for name, count in tally.items()
        if count >= threshold and not is_canonical(name)
    ]
    return sorted(candidates, key=lambda c: (-c.count, c.name))
