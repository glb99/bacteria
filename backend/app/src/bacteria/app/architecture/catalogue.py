"""The vocabulary this ontology is entitled to use.

Until now these words were string literals scattered through the parser that
happened to write them — ``"module"`` in one place, ``"imports"`` in another,
``"package"`` in three. That is the ontology **smeared into its adapter**, and
it is the arrangement the memory graph already learned not to keep: an
ungoverned ``rel`` produced ten names across fifteen rows in a fortnight, and
:mod:`bacteria.app.graph.catalogue` exists because of it.

It had not bitten here for one reason: a single module writes every one of
them. That is exactly the condition that held for ``rel`` right up until it
stopped holding.

**Separating the two is what makes this an ontology rather than an implication
of a parser.** Declared here, the model can be read without reading the code
that fills it, published, versioned, or handed to somebody writing a second
adapter for another language — which is the whole *one vocabulary, N adapters*
claim, and it cannot be true while the vocabulary lives inside one adapter.

**The meta-model is borrowed, the entries are not.** :class:`Relation` comes
from the graph package because the *shape* of a relation — a name, a sentence, a
signature, whether it is functional — is domain-neutral, and it is the clearest
instance so far of the split [dialogue 10 Q4] drew: the substrate travels, the
policy does not. Everything below is this domain's policy.

**Closed, with no tail, and here that is not a compromise.** The relation
catalogue keeps an unratified tail because a personal life produces words nobody
can enumerate in advance. These words come from a language specification and a
framework's conventions: ``module`` and ``import`` are Python's, ``table`` is
SQLModel's. There is nothing to discover, so there is nothing to leave a door
open for — and a tail here would only ever collect typos.

What *is* discovered lives in the graph instead, per instance: which words a
codebase repeats as roles, and which packages are features or layers. See
:mod:`~bacteria.app.architecture.classify`. So the type system is split
deliberately — given types here, discovered types as claims — and the seam is
the same given/discovered line the whole feature turns on.
"""

from typing import Optional

from bacteria.app.graph.catalogue import Relation

MODULE = "module"
PACKAGE = "package"
TABLE = "table"
WORD = "word"
"""A term the codebase repeats — ``service``, ``models``. Not a thing in the
code but a name the code keeps giving things, which is why it is its own kind
rather than a package with no modules."""

KIND = "kind"
"""What something is said to be — ``feature``, ``layer``, ``role``."""

KINDS: frozenset[str] = frozenset({MODULE, PACKAGE, TABLE, WORD, KIND})
"""Every node kind this ontology may mint.

Closed, and unlike ``_KINDS`` next door this closure needs no apology: a kind
here is either something Python has a word for or one of the two the
classification layer introduces. Nothing arrives from a model's imagination, so
nothing can arrive that is not on this list.

Kind participates in node identity — ``node_named(user_id, kind, label)`` — so a
drifting kind would split one package into two nodes. That argument is the same
one [dialogue 11 Q2] made for refusing the relation tail's treatment to kinds,
and it applies here with the extra comfort that the set is genuinely finite.
"""

CLASSIFICATIONS: frozenset[str] = frozenset({"feature", "layer", "role"})
"""What a subject may be said to be.

Deliberately small. A vocabulary of kinds-of-thing grows by proposal from
evidence, and today the evidence supports three; the fourth arrives when a
codebase repeatedly shows a shape none of these describe, not when somebody
thinks of a word.
"""


CATALOGUE: tuple[Relation, ...] = (
    Relation(
        name="imports",
        invariant=None,
        sentence="<src> imports <dst>",
        src_kind=MODULE,
        dst_kind=MODULE,
        # A module imports as many as it likes, and that is the whole subject.
        functional=False,
    ),
    Relation(
        name="in_package",
        invariant="A module lives in exactly one package.",
        sentence="<src> lives in <dst>",
        src_kind=MODULE,
        dst_kind=PACKAGE,
        # True by construction from the path, so nothing can currently violate
        # it. Declared anyway: an invariant that holds because of how the data
        # arrives is still an invariant, and the day a second adapter arrives it
        # is the first thing that could break.
        functional=True,
    ),
    Relation(
        name="owns_table",
        invariant=None,
        sentence="<src> declares <dst>",
        src_kind=MODULE,
        dst_kind=TABLE,
        functional=False,
    ),
    Relation(
        name="is_a",
        invariant="A subject is one kind of thing at a time.",
        sentence="<src> is a <dst>",
        # No source kind: a package is said to be a feature, and a word is said
        # to be a role. `None` means *any*, which is what `same_as` uses it for
        # next door and for the same reason -- the relation is about the claim,
        # not about what sort of thing is making it.
        src_kind=None,
        dst_kind=KIND,
        functional=True,
    ),
    Relation(
        name="is_not_a",
        invariant=None,
        sentence="<src> is not a <dst>",
        src_kind=None,
        dst_kind=KIND,
        # Emphatically not functional: disagreeing that a package is a feature
        # says nothing about whether it is a layer, and a person may reject
        # several proposals about one subject. Only agreement is exclusive.
        functional=False,
    ),
)

_BY_NAME: dict[str, Relation] = {relation.name: relation for relation in CATALOGUE}


def is_known(name: str) -> bool:
    """Is this a relation the architecture ontology has agreed to?

    Deliberately not called ``is_canonical``. That word belongs to the memory
    graph, where it distinguishes ratified vocabulary from an unratified tail
    kept as evidence. There is no tail here, so the question is not *has this
    earned its place* but *did somebody typo it*.
    """
    return name in _BY_NAME


def relation(name: str) -> Optional[Relation]:
    return _BY_NAME.get(name)


def functional() -> tuple[Relation, ...]:
    """The relations a subject may hold at most one of at a time.

    Nothing consumes this yet, which is why ``decisions.py`` still says no
    constraint can fire. Wiring it is passing this to ``observe`` — and the
    first contradiction it would catch is real: agreeing that a package is both
    a feature and a layer.
    """
    return tuple(r for r in CATALOGUE if r.functional)


def reads(name: str, src: str, dst: str) -> str:
    """One claim as a sentence, for a reader who did not write the relation.

    The same trick the memory catalogue uses, for the same reason: direction is
    otherwise invisible, and ``chat imports graph`` and ``graph imports chat``
    are different facts that look identical as a row of three columns.
    """
    known = _BY_NAME.get(name)
    if known is None:
        return f"{src} {name} {dst}"
    return known.sentence.replace("<src>", src).replace("<dst>", dst)
