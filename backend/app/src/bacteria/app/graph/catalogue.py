"""The shape a vocabulary has, and nothing any particular one says.

A relation has a name, a sentence, a kind signature and a flag saying whether it
can contradict itself. That shape is domain-neutral: ``mother`` and ``imports``
are the same kind of thing about different worlds. **Which relations exist is
not**, and the entries that used to sit here were a personal life's --
``employer``, ``mother``, ``lives_in`` -- declared in the substrate because for a
long time there was only one domain to declare them for.

The second domain made the seam visible by not using them.
:mod:`bacteria.app.architecture.catalogue` reached in for :class:`Relation` and
declared its own four words locally, and nine of the ten entries here turned out
to be one domain's policy living in everybody's package. They now live in
:mod:`bacteria.app.personal.catalogue`, where the domain that means them can be
read without reading the substrate.

**A vocabulary travels on the repository, not on an import.** :class:`Vocabulary`
is a value a caller constructs and hands to
:class:`~bacteria.app.graph.repository.SqlGraphRepository`, the same way the
ontology does and for the same reason it gives: fifteen call sites each
remembering to pass the right words is fifteen chances to judge one domain's
claim by another's rules. The service layer asks the repository rather than
importing a module-level literal, which is what let the entries move without
changing any of the eighty-two calls to ``observe`` and its siblings.

**The growth doctrine stays here** -- :data:`PROMOTION_THRESHOLD`,
:func:`promotable`, the tail. Those are rules *about* vocabularies rather than
entries in one, and they govern any domain whose words are discovered rather
than given. What moved is the list; what stayed is everything deciding how a
list may change.

Not built:
    Anywhere for an entry to come from. A domain's catalogue stays a literal for
    the reason the constraints it absorbed already gave: it moves to rows keyed
    by owner when an authoring route exists, since "a person has one employer" is
    exactly the kind of rule a particular person is entitled to disagree with.
"""

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class Vocabulary:
    """One domain's relations, and the questions a caller may ask about them.

    Frozen, and built once per domain rather than assembled per call: the two
    indexes below are the whole reason this is an object rather than a tuple,
    and rebuilding them inside a loop over the log is how a lookup becomes the
    expensive part of a read.

    ``names`` is the relation whose object is what to call its subject, or
    ``None`` where a domain has no such notion. It is a field rather than a
    constant in this module because *a claim about a name should relabel the
    node* is a personal-domain rule that happens to be executed by a substrate
    function -- architecture has no equivalent and must not inherit one by
    default.

    An empty vocabulary is a legitimate value rather than a missing one: a
    repository opened on a partition whose words nobody has declared can still
    read and write rows, it simply has no opinion about which of them
    contradict.
    """

    relations: tuple[Relation, ...] = ()
    names: Optional[str] = None

    _by_name: dict[str, Relation] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )
    _by_alias: dict[str, Resolution] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        # `object.__setattr__` because the dataclass is frozen and these are
        # derived rather than given.
        object.__setattr__(self, "_by_name", {r.name: r for r in self.relations})
        object.__setattr__(
            self,
            "_by_alias",
            {
                alias.name: Resolution(relation, alias.converse)
                for relation in self.relations
                for alias in relation.aliases
            },
        )

    def lookup(self, name: str) -> Optional[Relation]:
        """The entry for a relation name, or ``None`` if this domain has none.

        Exact match. Aliases are not consulted, because the callers that need it
        -- conflict evaluation, the console's rule list -- are asking about a
        relation as it was *recorded*, and an assertion's ``rel`` has already
        been canonicalized by the time it reaches the log.
        """
        return self._by_name.get(name)

    def is_canonical(self, name: str) -> bool:
        """Whether this domain agreed to the name, computed rather than stored.

        A column would make promotion an ``UPDATE`` across historical rows, which
        is an append-only log being mutated. Derived, promotion is an edit to a
        literal and every past row reclassifies for free.
        """
        return name in self._by_name

    def resolve(self, name: str) -> Optional[Resolution]:
        """Canonicalize a name a model proposed, or ``None`` for the tail.

        Entries first and aliases second, so a name that is both is read as
        itself. ``None`` is not a rejection: the caller records the claim under
        the model's own word, and this only says the vocabulary has nothing to
        say about it.
        """
        relation = self._by_name.get(name)
        if relation is not None:
            return Resolution(relation, swap=False)
        return self._by_alias.get(name)

    def functional(self) -> tuple[Relation, ...]:
        """Every relation that can produce a contradiction.

        The caller must not assume this is all of them: the admission test says a
        relation needs *something* able to check it, and an asymmetric kind
        signature qualifies on its own.
        """
        return tuple(relation for relation in self.relations if relation.functional)

    def preferences(self) -> tuple[Relation, ...]:
        """The relations a projection may turn into keyed memory.

        Functional and pointing at a value: the first because a key holds one
        answer, the second because a key holds a *word* rather than a reference
        to something else in the graph. ``mother`` is functional and is not a
        preference; ``pet`` points at a thing and is not either.
        """
        return tuple(r for r in self.relations if r.functional and r.dst_kind == "value")

    def describe(self) -> str:
        """The vocabulary as an extraction prompt states it.

        Rendered rather than written out beside the prompt, so the two cannot
        disagree. A prompt version hashing the prompt text therefore moves
        whenever this does, which is the property retraction wanted and could not
        have while the vocabulary was implicit in whatever the model chose.
        """
        lines = []
        for relation in self.relations:
            # A relation the extractor may not propose is not offered to it.
            # `same_as` is the case: a model suggesting merges would be guessing
            # in the one direction ADR 0006 calls unrecoverable. Converse aliases
            # are not advertised either -- they exist to recognize a name a model
            # reaches for unasked, and listing `mother_of` under a sentence
            # reading "<src> is the mother of <dst>" would invite exactly the
            # inversion the flag exists to undo.
            if not relation.extractable:
                continue
            synonyms = ", ".join(alias.name for alias in relation.aliases if not alias.converse)
            suffix = f" (also: {synonyms})" if synonyms else ""
            lines.append(f"  {relation.name} - {relation.sentence}{suffix}")
        return "\n".join(lines)


EMPTY = Vocabulary()
"""What a repository carries when nobody said which words apply.

Named rather than written as ``Vocabulary()`` at the default, so a reader of a
signature sees that *no vocabulary* is a decision somebody can make rather than
an oversight.
"""


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


def promotable(
    tally: dict[str, int],
    vocabulary: Vocabulary,
    *,
    threshold: int = PROMOTION_THRESHOLD,
) -> list[Candidate]:
    """Which relations outside the catalogue have earned a question.

    Pure, and takes the counts rather than fetching them, so the rule is testable
    without a database and the query is somewhere a query belongs.

    Sorted by how often each was seen, because a reader working down the list
    should meet the strongest case first — and ties by name, so two runs over
    unchanged data print the same thing and a diff means something.

    ``vocabulary`` is a parameter rather than a module-level lookup because
    *already canonical* is a question only a domain can answer, and this rule
    governs every domain whose words are discovered. Asked against the wrong
    vocabulary it proposes promoting words that are already in.
    """
    candidates = [
        Candidate(name, count)
        for name, count in tally.items()
        if count >= threshold and not vocabulary.is_canonical(name)
    ]
    return sorted(candidates, key=lambda c: (-c.count, c.name))
