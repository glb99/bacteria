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

ABOVE = "above"
"""The relation a stated layer order records.

**Nothing derives this, and the measurement is why.** `layerOf` in the console
ranks packages by longest path through `imports`, which is free, repeatable and
correct about the ordinary case. Run against this repository it puts fifteen of
nineteen packages in three adjacent bands at the ceiling: two cycles pump every
package downstream of them to the relaxation bound, and a cycle degrades not the
pair inside it but everything reachable from it. Derivation therefore fails
hardest exactly where a layered picture would help most.

So the order is testimony. Four layers here, and at most six statements -- fewer
if they chain -- against a count that cannot produce an axis at all.

**What it buys is a disagreement.** Height stated against imports derived means
an import can run *against* the order, and that is a boundary violation drawn
rather than tabulated: the edge leaves the floor and arrives at the roof.
`bacteria.app.core` imports two features today, which is the wart dialogue 14
recorded and left standing.
"""

SAME_AS = "same_as"
"""The relation a rename records.

Borrowed rather than invented: the substrate's identity rule already says
nodes are **linked, never merged**, and ``graph/service.py``'s ``link`` is
its writer. That module's docstring noted that nothing read the link yet and
that the first use would "look like a bug"; this is the first use, and it is
in the domain that needed it second.

A rename is exactly the claim ``same_as`` makes. ``bacteria.app.chat`` and
``bacteria.app.personal`` are one package under two names, both nodes keep
their ids and their history, and the judgment recorded against the old name
stays attached to it rather than being rewritten to pretend it was always
the new one.
"""

CLASSIFICATIONS: frozenset[str] = frozenset({"feature", "layer", "role"})
"""What a subject may be said to be.

Deliberately small. A vocabulary of kinds-of-thing grows by proposal from
evidence, and today the evidence supports three; the fourth arrives when a
codebase repeatedly shows a shape none of these describe, not when somebody
thinks of a word.
"""


# Not here: `in_package`. A module's package is its own name minus the last
# segment, so the relation carries no information the node does not already
# have, and nothing traverses it. Declaring one nothing emits is how a catalogue
# becomes a description of what somebody hoped rather than of what exists --
# which it briefly was, along with `owns_table`, until the two were checked.
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
    Relation(
        name="same_as",
        invariant=None,
        sentence="<src> is <dst> under a new name",
        # No kinds, because a rename relates two of whatever the pair both are.
        # A package renamed and a word renamed are the same act, and `link`
        # refuses a mismatched pair on its own.
        src_kind=None,
        dst_kind=None,
        # A name can be superseded more than once -- `chat` to `personal` to
        # whatever comes next -- and every hop is worth keeping, because a
        # decision recorded under the first name has to find its way to the last.
        functional=False,
    ),
    Relation(
        name="above",
        # Not an invariant, because the thing that would be checked here is not
        # a property of one assertion. A cycle -- two layers each said to be over
        # the other -- involves several rows and is broken at read time, the way
        # `same_as` chains are, rather than refused at write time on a row that
        # is individually fine.
        invariant=None,
        sentence="<src> sits above <dst>",
        # Packages at both ends, which the meta-model can say. What it cannot
        # say is the rule that matters: both ends must be packages somebody has
        # agreed are *layers*. `Relation` constrains kinds, and a classification
        # is a judgment rather than a kind -- so that check lives in the writer,
        # and this is the first relation in either domain whose validity depends
        # on another assertion rather than on the meta-model alone.
        src_kind=PACKAGE,
        dst_kind=PACKAGE,
        # A layer may sit above several. The order is a partial one and saying
        # otherwise would refuse the second statement about a floor that holds
        # up two things.
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
