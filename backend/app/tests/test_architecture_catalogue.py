"""The architecture ontology's declared vocabulary.

Small, and most of it guards the thing the file exists for: that the model is
readable without reading the adapter, and that the adapter cannot drift from it.
"""

from bacteria.app.architecture import decisions, derive
from bacteria.app.architecture.catalogue import (
    CATALOGUE,
    CLASSIFICATIONS,
    KINDS,
    functional,
    is_known,
    reads,
    relation,
)
from bacteria.app.architecture.classify import propose
from bacteria.app.architecture.derive import Derived, Import, Module


class TestVocabulary:
    def test_every_relation_names_kinds_the_ontology_has(self) -> None:
        """A signature naming a kind that cannot exist is a rule nothing can break.

        It would also pass every check forever while quietly matching nothing,
        which is the shape of a guard that looks present and is not.
        """
        for entry in CATALOGUE:
            for kind in (entry.src_kind, entry.dst_kind):
                assert kind is None or kind in KINDS, entry.name

    def test_a_claim_reads_as_a_sentence(self) -> None:
        """Direction is invisible in three columns and obvious in a sentence.

        ``chat imports graph`` and ``graph imports chat`` are different facts
        that look identical as a row, which is the whole reason the memory
        catalogue carries sentences too.
        """
        assert reads("imports", "chat.service", "graph.log") == "chat.service imports graph.log"
        assert reads("is_a", "app.chat", "feature") == "app.chat is a feature"

    def test_an_unknown_relation_still_reads(self) -> None:
        """A typo must degrade to something legible, not to an exception.

        The renderer runs over whatever is in the log, including rows written
        before a relation was renamed.
        """
        assert reads("improts", "a", "b") == "a improts b"

    def test_agreement_is_exclusive_and_disagreement_is_not(self) -> None:
        """A subject is one kind of thing; it can be denied several.

        Rejecting *feature* says nothing about *layer*, so only ``is_a`` is
        functional. Getting this backwards would make a second rejection close
        the first and lose it.
        """
        exclusive = {entry.name for entry in functional()}

        assert "is_a" in exclusive
        assert "is_not_a" not in exclusive

    def test_the_classifier_proposes_only_declared_classifications(self) -> None:
        """The declared kinds-of-thing and the ones the classifier emits agree.

        Driven through the classifier rather than asserted against a literal.
        The first version of this test restated the constant and would have
        passed while the two files disagreed, which is the failure it was
        written to catch — a proposal naming a word the ontology does not
        declare stores claims nothing else can interpret.
        """
        derived = Derived(
            modules={
                name: Module(
                    name=name,
                    path=name.replace(".", "/") + ".py",
                    package=name.rsplit(".", 1)[0],
                    tables=(),
                )
                for name in (
                    "app.a.service",
                    "app.b.service",
                    "app.c.service",
                    "app.a.models",
                    "app.b.models",
                    "app.c.models",
                    "app.core.db",
                    "app.core.settings",
                )
            },
            imports=tuple(
                Import(src=f"app.{f}.service", dst="app.core.db", deferred=False, line=1)
                for f in ("a", "b", "c")
            ),
        )

        emitted = {proposal.claim for proposal in propose(derived)}

        assert emitted
        assert emitted <= CLASSIFICATIONS


class TestTheAdapterUsesIt:
    def test_every_declared_derived_relation_is_actually_emitted(self) -> None:
        """Declared and emitted are the same set, in both directions.

        The first version checked only one direction — that the adapter's
        constants are declared names — and passed while ``in_package`` and
        ``owns_table`` were declared and emitted by nothing at all. A catalogue
        listing relations no adapter produces describes what somebody hoped for,
        not what exists.
        """
        emitted = set(derive.RELATIONS)
        derived_relations = {
            entry.name for entry in CATALOGUE if entry.name not in {"is_a", "is_not_a"}
        }

        assert emitted == derived_relations

    def test_the_parser_writes_only_declared_relations(self) -> None:
        for name in derive.RELATIONS:
            assert is_known(name), name

    def test_the_parser_mints_only_declared_kinds(self) -> None:
        """A drifting kind splits one package into two nodes.

        Kind participates in node identity, so this is the failure that cannot
        be repaired by renaming afterwards.
        """
        assert set(derive.KINDS) <= KINDS

    def test_judgments_use_declared_relations_and_kinds(self) -> None:
        """The write path and the read path have to mean the same words."""
        assert is_known(decisions.AGREE)
        assert is_known(decisions.DISAGREE)

    def test_a_relation_is_retrievable_by_name(self) -> None:
        """Whatever consumes the invariant needs the entry, not just its name."""
        found = relation("is_a")

        assert found is not None
        assert found.invariant == "A subject is one kind of thing at a time."
