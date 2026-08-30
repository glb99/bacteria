"""What a codebase calls things, learned from what it repeats.

The one tier of this feature that is about a *particular* codebase, so it is
also the only one whose output a person can reasonably disagree with. These
check the disagreeable part: that a convention needs evidence, that the evidence
travels, and that a repository which has adopted no conventions is told so
rather than given some.
"""

from pathlib import Path

from bacteria.app.architecture.classify import propose, roles, sentence
from bacteria.app.architecture.derive import Derived, Import, Module


def _repo(*modules: str, imports: tuple[tuple[str, str], ...] = ()) -> Derived:
    return Derived(
        modules={
            name: Module(
                name=name,
                path=name.replace(".", "/") + ".py",
                package=name.rsplit(".", 1)[0] if "." in name else name,
                tables=(),
            )
            for name in modules
        },
        imports=tuple(Import(src=src, dst=dst, deferred=False, line=1) for src, dst in imports),
    )


class TestRoles:
    def test_a_name_in_three_packages_is_a_convention(self) -> None:
        """Three is the threshold, matching the relation catalogue's.

        Two occurrences are a coincidence and a codebase is entitled to one
        accident; calling that a convention puts a word in the model that
        nobody adopted.
        """
        derived = _repo("app.a.service", "app.b.service", "app.c.service")

        assert [role.name for role in roles(derived)] == ["service"]

    def test_a_name_in_two_packages_is_not(self) -> None:
        """The threshold has to be seen refusing, or it is not a threshold."""
        derived = _repo("app.a.service", "app.b.service")

        assert roles(derived) == ()

    def test_a_name_repeated_inside_one_package_is_not_a_convention(self) -> None:
        """Counted by package, never by module.

        A convention is a thing that recurs across places. Counting modules
        would let one package holding several similarly-named files invent a
        vocabulary for the whole repository.
        """
        derived = _repo("app.a.service", "app.a.sub.service", "app.a.deep.service")

        assert [role.name for role in roles(derived)] == ["service"]
        assert roles(derived)[0].packages == 3

    def test_dunder_modules_are_never_roles(self) -> None:
        """Every package has an ``__init__``, so it would win in every repository.

        A "convention" present everywhere distinguishes nothing, and it would be
        the top proposal in every project this is ever pointed at.
        """
        derived = _repo("app.a.__init__", "app.b.__init__", "app.c.__init__")

        assert roles(derived) == ()

    def test_the_evidence_travels_with_the_role(self) -> None:
        """A proposal nobody can check is one they approve without checking.

        That is the review-fatigue failure arriving as a convenience: a queue
        everyone clicks through is worse than no queue, because everyone
        believes it was checked.
        """
        derived = _repo("app.a.service", "app.b.service", "app.c.service")

        assert roles(derived)[0].modules == ("app.a.service", "app.b.service", "app.c.service")


class TestProposals:
    def test_one_proposal_per_word_not_per_module(self) -> None:
        """The rule of three promotes a vocabulary word, not each instance.

        The first version emitted a claim per module — forty-one proposals for
        this repository, which is a queue nobody reads and therefore a queue
        everybody approves. The catalogue admits ``pet``, not each claim about
        a pet.
        """
        derived = _repo("app.a.service", "app.b.service", "app.c.service", "app.d.service")

        role_claims = [p for p in propose(derived) if p.claim == "role"]

        assert len(role_claims) == 1
        assert role_claims[0].subject == "service"

    def test_a_package_carrying_the_conventions_is_a_feature(self) -> None:
        """Carrying what the codebase repeats is what makes a package a feature."""
        derived = _repo(
            "app.a.service",
            "app.b.service",
            "app.c.service",
            "app.a.models",
            "app.b.models",
            "app.c.models",
        )

        features = [p.subject for p in propose(derived) if p.claim == "feature"]

        assert features == ["app.a", "app.b", "app.c"]

    def test_a_depended_on_package_with_no_conventions_is_a_layer(self) -> None:
        """Depended on rather than owning anything is what a layer is here."""
        derived = _repo(
            "app.a.service",
            "app.b.service",
            "app.c.service",
            "app.a.models",
            "app.b.models",
            "app.c.models",
            "app.core.db",
            "app.core.settings",
            imports=(
                ("app.a.service", "app.core.db"),
                ("app.b.service", "app.core.db"),
                ("app.c.service", "app.core.db"),
            ),
        )

        layers = [p.subject for p in propose(derived) if p.claim == "layer"]

        assert layers == ["app.core"]

    def test_a_package_of_one_module_is_not_classified(self) -> None:
        """Namespace roots and leaf directories say nothing about the design.

        They were most of the noise in the first version: ``bacteria``,
        ``bacteria.agent`` and ``app.alembic.versions`` all arrived as claims.
        """
        derived = _repo(
            "app.a.service",
            "app.b.service",
            "app.c.service",
            "app.a.models",
            "app.b.models",
            "app.c.models",
            "app.lonely.only",
        )

        assert "app.lonely" not in [p.subject for p in propose(derived)]

    def test_a_repository_with_no_conventions_is_told_so(self) -> None:
        """Silence is the honest answer, and it has to be reachable.

        Inventing a taxonomy for a project that adopted none is how a model
        acquires types nobody meant — and the earlier version did exactly that,
        calling every unclassifiable package a ``library``, which made the
        remainder a bucket named after what it is not.
        """
        derived = _repo("app.main", "app.helpers", "app.thing")

        assert propose(derived) == ()

    def test_a_proposal_reads_as_a_sentence(self) -> None:
        """Agreement is worthless if the thing agreed to is a tuple."""
        derived = _repo("app.a.service", "app.b.service", "app.c.service")

        assert sentence(propose(derived)[0]) == "service is a role"


class TestAgainstThisRepository:
    def test_this_codebase_proposes_its_own_conventions(self) -> None:
        """The real check: does it find what a reader would say is there?

        Written against this repository because its conventions are known —
        ``models``, ``views``, ``repository``, ``service`` and ``tasks`` — and a
        classifier that missed them would be wrong in a way no synthetic fixture
        would reveal.
        """
        from bacteria.app.architecture.derive import derive
        from bacteria.app.architecture.layout import source_roots

        repo = Path(__file__).resolve().parents[3]
        derived = derive(source_roots(repo))

        found = {role.name for role in roles(derived)}
        assert {"models", "repository", "service", "views"} <= found

        features = {p.subject for p in propose(derived) if p.claim == "feature"}
        assert "bacteria.app.personal" in features
        assert "bacteria.app.graph" in features

        layers = {p.subject for p in propose(derived) if p.claim == "layer"}
        assert "bacteria.app.core" in layers
