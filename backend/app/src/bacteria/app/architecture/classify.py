"""What this codebase calls things, learned from what it repeats.

Everything in :mod:`~bacteria.app.architecture.derive` is given by the language:
``module``, ``package`` and ``import`` come from Python and ``table`` from
SQLModel, and any repository yields the same words. **None of it is about this
codebase.** A parse of one project and a parse of another differ only in their
contents.

This module is the other half, and it is the only part of the feature that is
about *a particular* codebase. ``feature``, ``layer`` and ``role`` appear in no
language specification. They are conventions somebody adopted, they differ from
project to project, and the only way to find them is to notice what repeats.

**Which is where the rule of three finally applies.** The schema-growth doctrine
-- propose on the third sighting, ratify by hand -- was written about testimony,
and this package argued at length that it does not govern a vocabulary handed
down by a grammar. It governs *this* tier exactly, because nothing hands these
down.

**And this is the first uncertain thing here.** ``chat.service imports
graph.log`` is exact and not worth arguing about. *"chat is a feature"* is a
judgment drawn from a regularity, it can be wrong, and a person may disagree --
which is why everything below is a :class:`Proposal` and nothing is a fact. It
is also why the confirmation machinery this domain seemed to have no use for
turns out to have one.

Not built:
    Any weighing beyond counting. A proposal carries how much evidence it has
    and no score, because a number between zero and one invites a threshold and
    a threshold is a decision made by whoever picked it rather than by the
    person the model belongs to.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from bacteria.app.architecture.derive import Derived

RULE_OF_THREE = 3
"""How many packages must share a module name before it is called a role.

The same threshold the relation catalogue promotes on, for the same reason: two
occurrences are a coincidence and a codebase is entitled to one accident. It is
a parameter everywhere it is used, because a small repository has fewer chances
to repeat itself and its owner is the one who knows whether twice is enough.
"""


@dataclass(frozen=True)
class Role:
    """A module name this codebase keeps using, and where.

    ``modules`` is the whole evidence rather than a count, because a proposal a
    person cannot check is a proposal they will accept without checking -- which
    is the review-fatigue failure the design warns about, arriving as a
    convenience.
    """

    name: str
    modules: tuple[str, ...]

    @property
    def packages(self) -> int:
        return len({module.rsplit(".", 1)[0] for module in self.modules})


@dataclass(frozen=True)
class Proposal:
    """One claim about this codebase that a person may accept or reject.

    ``relation`` and ``claim`` are kept apart so that a reader sees the sentence
    rather than a tuple: *chat* ``is_a`` *feature*, *chat.service* ``has_role``
    *service*. It is the same shape the relation catalogue gives a claim about a
    person, and deliberately so -- one surface renders both.

    ``because`` is the evidence in a sentence. Nothing else in this system asks
    somebody to agree with a computation, and the computation has to be legible
    or the agreement is worthless.
    """

    subject: str
    relation: str
    claim: str
    because: str


def roles(derived: Derived, *, threshold: int = RULE_OF_THREE) -> tuple[Role, ...]:
    """Module names that recur across packages often enough to be a convention.

    Counted by *package*, not by module. Counting modules would make a package
    holding ``service.py`` twice look like a convention, and a convention is
    precisely a thing that recurs across places rather than within one.

    ``__init__`` is excluded: every package has one, so it would be the
    strongest "role" in every repository and mean nothing.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for module in derived.modules.values():
        leaf = module.name.rsplit(".", 1)[-1]
        if leaf == module.name or leaf.startswith("_"):
            continue
        seen[leaf].add(module.name)

    found = [
        Role(name=name, modules=tuple(sorted(modules)))
        for name, modules in seen.items()
        if len({m.rsplit(".", 1)[0] for m in modules}) >= threshold
    ]
    return tuple(sorted(found, key=lambda role: (-role.packages, role.name)))


def propose(derived: Derived, *, threshold: int = RULE_OF_THREE) -> tuple[Proposal, ...]:
    """Everything this codebase's own shape suggests about itself.

    **One proposal per word, not per instance.** The first version emitted a
    ``has_role`` claim for every module carrying a repeated name -- forty-one
    proposals for this repository, which is a queue nobody reads and therefore a
    queue everybody approves. The rule of three promotes a *vocabulary word*;
    the relation catalogue admits ``pet``, not each claim about a pet. So the
    question put to a person is *"is ``service`` a role here"* once, with its
    evidence, rather than thirty times.

    **Nothing is proposed without positive evidence.** A package carrying the
    repeated names is a feature; one carrying none that many packages depend on
    is a layer; anything else gets **no proposal at all**. The first version
    called that remainder a ``library``, which made it the answer for every leaf
    directory and every namespace root -- a bucket named after what it is not,
    which is the Misnomer the anti-pattern list warns about.

    A repository with no repetition yields nothing, which is the honest answer.
    Inventing a taxonomy for a project that has not adopted one is how a model
    acquires types nobody meant.
    """
    found = roles(derived, threshold=threshold)
    if not found:
        return ()

    proposals: list[Proposal] = [
        Proposal(
            subject=role.name,
            relation="is_a",
            claim="role",
            because=(
                f"{role.packages} packages have a {role.name} module — "
                f"{', '.join(role.modules[:4])}"
                + (f" and {len(role.modules) - 4} more" if len(role.modules) > 4 else "")
            ),
        )
        for role in found
    ]

    by_name = {role.name: role for role in found}
    carried: dict[str, set[str]] = defaultdict(set)
    for module in derived.modules.values():
        leaf = module.name.rsplit(".", 1)[-1]
        if leaf in by_name and module.name != leaf:
            carried[module.name.rsplit(".", 1)[0]].add(leaf)

    fan_in = _fan_in(derived)
    sizes = _sizes(derived)
    typical = _typical(carried)

    for package in sorted({module.package for module in derived.modules.values()}):
        # A package of one module is a namespace root or a leaf directory, and
        # classifying it says nothing about the design. They were most of the
        # noise: `bacteria`, `bacteria.agent`, `app.alembic.versions`.
        if sizes.get(package, 0) < 2:
            continue

        held = carried.get(package, set())
        if held and len(held) >= max(2, typical - 1):
            proposals.append(
                Proposal(
                    subject=package,
                    relation="is_a",
                    claim="feature",
                    because=(
                        f"carries {', '.join(sorted(held))} — "
                        f"{len(held)} of the {len(by_name)} roles this codebase repeats"
                    ),
                )
            )
        elif not held and fan_in.get(package, 0) >= threshold:
            proposals.append(
                Proposal(
                    subject=package,
                    relation="is_a",
                    claim="layer",
                    because=(
                        f"carries none of the roles and {fan_in[package]} packages "
                        f"import it — depended on rather than owning anything"
                    ),
                )
            )

    return tuple(proposals)


def _sizes(derived: Derived) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for module in derived.modules.values():
        counts[module.package] += 1
    return counts


def _typical(carried: dict[str, set[str]]) -> int:
    """How many roles a package that has any usually has.

    A fixed number would be this codebase's shape imposed on every other. The
    median of what actually recurs is the repository describing itself, which is
    the whole point of the tier.
    """
    counts = sorted(len(held) for held in carried.values() if held)
    if not counts:
        return 0
    return counts[len(counts) // 2]


def _fan_in(derived: Derived) -> dict[str, int]:
    """How many other packages import each package, counted once per package."""
    into: dict[str, set[str]] = defaultdict(set)
    place = {module.name: module.package for module in derived.modules.values()}
    for edge in derived.imports:
        source = place.get(edge.src)
        target = place.get(edge.dst)
        if source and target and source != target:
            into[target].add(source)
    return {name: len(sources) for name, sources in into.items()}


def sentence(proposal: Proposal) -> str:
    """A proposal as a reader sees it, so agreeing with one means something."""
    verb = "is a" if proposal.relation == "is_a" else "has the role"
    return f"{proposal.subject} {verb} {proposal.claim}"


def summarise(proposals: Sequence[Proposal]) -> str:
    kinds = defaultdict(int)
    for proposal in proposals:
        kinds[proposal.claim] += 1
    return ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
