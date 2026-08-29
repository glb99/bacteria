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
from bacteria.app.architecture.views import ClassificationOut, ImportOut, ModelOut, ModuleOut


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


CARRIED_BY: dict[str, tuple[str, type, tuple[str, ...]]] = {
    # relation -> (field on ModelOut, item model, fields that carry the edge)
    "imports": ("imports", ImportOut, ("src", "dst")),
    # Flattened rather than listed: a module carries the tables it declares,
    # so the edge is `ModuleOut.name` x each entry of `ModuleOut.tables`.
    "owns_table": ("modules", ModuleOut, ("name", "tables")),
    # Both judgments ride one field. `verdict` is what separates them, which
    # is why it is named here: drop it and `is_a` and `is_not_a` become
    # indistinguishable on the wire while both still look carried.
    "is_a": ("proposals", ClassificationOut, ("subject", "claim", "verdict")),
    "is_not_a": ("proposals", ClassificationOut, ("subject", "claim", "verdict")),
}
"""How each declared relation reaches a client, if it does.

Relation -> the field on ``ModelOut``, the item model, and the fields that
carry the edge.
"""


class TestTheWireFormatCarriesIt:
    """The seam between the declared ontology and what a client actually reads.

    ``read_model`` never imports this catalogue. It does not mint anything, so
    the closed ``KINDS`` set cannot be violated there — but it is the only view
    of this ontology any client has, and it was written independently of the
    words the ontology declares. ``ModelOut`` is a nested document rather than
    triples: ``imports`` matches a relation name by coincidence, and
    ``owns_table`` does not appear at all, being flattened into
    ``ModuleOut.tables``.

    So the catalogue could go on declaring a relation the API had quietly
    stopped expressing, and nothing would say so. That is the defect PR #87
    fixed by hand for the adapter — ``in_package`` and ``owns_table`` declared
    and emitted by nothing — arriving through the other door.
    """

    def test_every_declared_relation_reaches_a_client(self) -> None:
        """Adding a relation to the catalogue must fail until somebody sends it.

        The point is the failure, not the pass. A relation declared and never
        serialised is invisible to every consumer of this ontology, which makes
        the catalogue a description of what somebody hoped for — the exact
        wording the adapter's own guard uses, for the same reason.
        """
        assert set(CARRIED_BY) == {entry.name for entry in CATALOGUE}

    def test_the_fields_that_carry_each_relation_exist(self) -> None:
        """Renaming a field on the wire breaks the mapping above, loudly.

        Checked against ``model_fields`` rather than by serialising a response,
        because the contract is the schema: a client reads these names, and a
        rename is exactly the silent drift this class exists to catch.
        """
        for name, (on_model, item, fields) in CARRIED_BY.items():
            assert on_model in ModelOut.model_fields, f"{name}: ModelOut.{on_model}"
            for field in fields:
                assert field in item.model_fields, f"{name}: {item.__name__}.{field}"
