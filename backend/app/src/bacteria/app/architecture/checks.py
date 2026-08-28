"""The boundaries this codebase has agreed to, and what can decide them.

Everything in :mod:`~bacteria.app.architecture.derive` is read off the grammar
and nobody chose it. Everything here was *stated by a person* — the sentences
come from ``CLAUDE.md``'s "Boundaries not to erode" — and that is the whole
distinction the feature exists to hold. A derived fact is not contestable; a
boundary is a claim somebody made and may later be wrong about.

**A literal, for the reason the relation catalogue gives.** ``CATALOGUE`` says
it stays a literal until an authoring route exists, since a rule is exactly the
sort of thing its owner is entitled to disagree with. Same here, and the same
destination: rows keyed by scope, with a date stated and a date retired, so that
retiring a boundary is an event rather than a deletion from a file.

**A boundary that nothing can decide is still recorded.** :attr:`Boundary.decides`
is ``None`` for the four that are about what a module *contains* or how it
*calls*, which no import graph can see. Leaving them out would be the more
convenient design and it would make this a monitor that reports a clean bill of
health on questions it never asked. Four of the seven are in that state, and a
reader has to be able to see that.

Not built:
    Any way for a crossing to be accepted. That is the stated layer above this
    one -- an append saying *this edge is fine and here is why* -- and it needs
    somewhere to write, which this module deliberately does not have. Until it
    exists a boundary is either clean or crossed, with no third state.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from bacteria.app.architecture.derive import Derived, Import

AGENT = "bacteria.agent"
APP = "bacteria.app"
CORE = "bacteria.app.core"
INTERFACES = "bacteria.agent.interfaces"

Rule = Callable[[Derived], Iterable[Import]]
"""Selects the edges that cross a boundary. Yields nothing when it holds."""


@dataclass(frozen=True)
class Boundary:
    """One rule somebody stated about how this codebase may be arranged.

    ``sentence`` is the wording a person wrote, kept verbatim rather than
    paraphrased into a rule name. It is what makes the boundary contestable: a
    reader cannot disagree with ``core_imports_features`` and can disagree with
    *"core/ holds nothing that names a domain concept"*. The relation catalogue
    made the same choice for the same reason.

    ``decides`` is ``None`` when no import can settle the question. That is not
    a gap to be filled later by a cleverer check -- *entrypoints hold
    configuration, never logic* is about a module's contents, and a dependency
    graph has no opinion about contents.

    ``elsewhere`` names what does check it, where something does. Without it an
    undecidable boundary reads as unguarded, and two of these are in fact
    guarded by tests that have nothing to do with this feature.

    ``about`` names the module regions the rule speaks about. A boundary whose
    regions are absent from a codebase is **inapplicable**, not satisfied:
    pointed at somebody else's repository, *"the agent knows nothing about the
    application"* came back ``holds`` because neither package existed. A rule
    that passes by describing nothing is the vacuous truth this feature reports
    ``undecidable`` to avoid, arriving through a different door.
    """

    name: str
    sentence: str
    decides: Rule | None = None
    elsewhere: str | None = None
    about: tuple[str, ...] = ()

    def applies_to(self, derived: Derived) -> bool:
        """Whether this codebase contains what the rule is about."""
        return all(derived.within(prefix) for prefix in self.about)


@dataclass(frozen=True)
class Crossing:
    """One edge that breaks one boundary.

    Carries the whole :class:`Import` rather than a formatted string, so that a
    caller can report the file and line. A finding somebody cannot navigate to
    is a finding they will not act on.
    """

    boundary: Boundary
    edge: Import


@dataclass(frozen=True)
class Verdict:
    """What was checked, what was not, and why.

    ``undecidable`` is returned rather than dropped for the reason the module
    docstring gives: a report that lists only passes and failures implies it
    looked at everything, and this one looked at three of seven.
    """

    held: tuple[Boundary, ...]
    crossings: tuple[Crossing, ...]
    undecidable: tuple[Boundary, ...]
    inapplicable: tuple[Boundary, ...] = ()

    @property
    def clean(self) -> bool:
        """True when every boundary that *could* be decided came back clean."""
        return not self.crossings


def _agent_reaches_into_the_app(derived: Derived) -> Iterable[Import]:
    for edge in derived.imports:
        if edge.src.startswith(f"{AGENT}.") and edge.dst.startswith(f"{APP}."):
            yield edge


def _app_reaches_the_agents_own_root(derived: Derived) -> Iterable[Import]:
    for edge in derived.imports:
        if edge.src.startswith(f"{APP}.") and (
            edge.dst == INTERFACES or edge.dst.startswith(f"{INTERFACES}.")
        ):
            yield edge


def _core_names_a_domain_concept(derived: Derived) -> Iterable[Import]:
    """Core importing a feature, at module level only.

    The deferred exemption is the one piece of judgment in this file and it is
    load-bearing. ``core/jobs.py`` imports three task modules inside a function
    because procrastinate discovers tasks by import side effect, and a producer
    that never imports one cannot enqueue against it. That is a deliberate
    deferral with its reasoning written beside it, not a layer being eroded --
    and a check that cannot tell the two apart reports six violations on a
    codebase whose boundary is intact, which is how a useful gate becomes one
    everybody disables.
    """
    for edge in derived.imports:
        if edge.deferred:
            continue
        in_core = edge.src == CORE or edge.src.startswith(f"{CORE}.")
        into_app = edge.dst.startswith(f"{APP}.")
        outside_core = not (edge.dst == CORE or edge.dst.startswith(f"{CORE}."))
        if in_core and into_app and outside_core:
            yield edge


def _core_declares_a_table(derived: Derived) -> Iterable[Import]:
    """A table declared anywhere in ``core/``.

    Yields a self-edge rather than a real import, because the offence is a
    declaration and not a dependency. That is a small dishonesty in the return
    type and the alternative is a second finding shape for one rule; if a third
    such check ever appears, this is the one that should force the split.
    """
    for module in derived.modules.values():
        if not module.tables:
            continue
        if module.name == CORE or module.name.startswith(f"{CORE}."):
            for table in module.tables:
                yield Import(src=module.name, dst=table, deferred=False, line=0)


BOUNDARIES: tuple[Boundary, ...] = (
    Boundary(
        name="the-agent-knows-nothing-of-the-application",
        sentence="The application depends on the agent; the agent knows nothing about the application.",
        decides=_agent_reaches_into_the_app,
        about=(AGENT, APP),
    ),
    Boundary(
        name="two-composition-roots",
        sentence="The application never imports bacteria.agent.interfaces.",
        decides=_app_reaches_the_agents_own_root,
        about=(APP, INTERFACES),
    ),
    Boundary(
        name="core-names-no-domain-concept",
        sentence="Features own their tables, tasks, and routes. core/ holds nothing that names a domain concept.",
        decides=_core_names_a_domain_concept,
        about=(CORE,),
    ),
    Boundary(
        name="features-own-their-tables",
        sentence="Features own their tables, so core/ declares none.",
        decides=_core_declares_a_table,
        about=(CORE,),
    ),
    Boundary(
        name="entrypoints-hold-configuration",
        sentence="Entrypoints hold configuration, never logic.",
        elsewhere="nothing — they are omitted from coverage, so logic there is untested by rule",
    ),
    Boundary(
        name="jobs-enqueue-in-the-callers-transaction",
        sentence="Jobs are enqueued inside the caller's transaction.",
        elsewhere="nothing — the reason the queue is Postgres rather than Redis, guarded by review",
    ),
    Boundary(
        name="migrations-own-the-schema",
        sentence="Migrations own the schema. Nothing creates tables at startup.",
        elsewhere="tests/test_migrations.py — asserts migrations and models agree",
    ),
    Boundary(
        name="authentication-is-not-authorization",
        sentence="auth/ answers who is calling and nothing else; whether they may have a resource is decided next to that resource.",
        elsewhere="ADR 0004 — and ingestion never wrote an ownership rule, which that record states",
    ),
)


def evaluate(derived: Derived, boundaries: Sequence[Boundary] = BOUNDARIES) -> Verdict:
    """Judge a derived graph against the boundaries somebody stated about it.

    ``boundaries`` is a parameter with a default for the same reason
    ``observe`` takes its relations that way: a test needs to drive one rule
    over a hand-built graph, and a module-level literal makes every test a test
    of this codebase's current shape.
    """
    held: list[Boundary] = []
    crossings: list[Crossing] = []
    undecidable: list[Boundary] = []
    inapplicable: list[Boundary] = []

    for boundary in boundaries:
        if boundary.decides is None:
            undecidable.append(boundary)
        elif not boundary.applies_to(derived):
            inapplicable.append(boundary)
        elif found := [
            Crossing(boundary=boundary, edge=edge) for edge in boundary.decides(derived)
        ]:
            crossings.extend(found)
        else:
            held.append(boundary)

    return Verdict(
        held=tuple(held),
        crossings=tuple(crossings),
        undecidable=tuple(undecidable),
        inapplicable=tuple(inapplicable),
    )
