"""The architecture ontology's declared vocabulary.

Small, and most of it guards the thing the file exists for: that the model is
readable without reading the adapter, and that the adapter cannot drift from it.
"""

from typing import Optional

from bacteria.app.architecture import decisions, derive
from bacteria.app.architecture.catalogue import (
    CATALOGUE,
    CLASSIFICATIONS,
    DERIVED,
    KINDS,
    STATED,
    functional,
    is_known,
    reads,
    relation,
)
from bacteria.app.architecture.classify import propose
from bacteria.app.architecture.derive import Derived, Import, Module
from bacteria.app.architecture.views import (
    ClassificationOut,
    ImportOut,
    ModelOut,
    ModuleOut,
    OrphanOut,
)


class TestVocabulary:
    def test_every_relation_names_kinds_the_ontology_has(self) -> None:
        """A signature naming a kind that cannot exist is a rule nothing can break.

        It would also pass every check forever while quietly matching nothing,
        which is the shape of a guard that looks present and is not.
        """
        for entry in CATALOGUE:
            for kind in (entry.src_kind, entry.dst_kind):
                assert kind is None or kind in KINDS, entry.name

    def test_every_functional_relation_can_state_its_rule(self) -> None:
        """A rule a person cannot read is a rule they cannot disagree with.

        The personal catalogue has had this guard since ADR 0007; this one did
        not, and the second domain inheriting the first's vocabulary without its
        discipline is the shape of nearly every defect found here. ``sentence``
        says which way round to read a claim, ``invariant`` says what cannot be
        true twice, and only the second is any use to somebody being shown a
        contradiction.
        """
        for entry in CATALOGUE:
            if entry.functional:
                assert entry.invariant, f"{entry.name} is functional and states no rule"

    def test_a_relation_states_a_rule_only_when_it_has_one(self) -> None:
        """An invariant on a relation nothing constrains is a rule with no check.

        It reads as governed and is not, which is worse than a blank field: a
        reader trusts the sentence and no code ever tests it.
        """
        for entry in CATALOGUE:
            if not entry.functional:
                assert entry.invariant is None, entry.name

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


"""Relations a person writes, which no parse can produce.

Excluded from the adapter's guard rather than listed inside it, because the
distinction is the whole feature: a parse is repeatable and a judgment is not.
``same_as`` joined them when renames arrived -- whether a package vanished or
changed its name is exactly what a parse cannot tell, which is why a person has
to say. ``above`` joined for a stronger reason: a parse *can* rank packages by
their imports, and on this repository the ranking collapses -- fifteen of
nineteen in three adjacent bands, because two cycles pump everything downstream
of them to the bound. Derivable and useless is why that axis is testimony.
"""


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
        derived_relations = {entry.name for entry in CATALOGUE} - STATED

        assert emitted == derived_relations
        assert derived_relations == DERIVED

    def test_the_parser_writes_only_declared_relations(self) -> None:
        for name in derive.RELATIONS:
            assert is_known(name), name

    def test_the_parser_mints_only_declared_kinds(self) -> None:
        """The adapter's manifest of kinds stays inside the declared set.

        Kind participates in node identity -- ``node_named(user_id, kind,
        label)`` -- so a drifting kind would split one package into two nodes
        and could not be repaired by renaming afterwards. That is the failure
        this guards *against*, and it is worth being exact about how far the
        guard reaches: nothing in this feature mints a node today. The model is
        reparsed per request and only judgments are written, so ``derive.KINDS``
        is a manifest rather than something the parser consults, and this
        compares two declarations. It becomes a check on behaviour the moment
        anything here writes a node, which is why it is written now rather than
        then.
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


CARRIED_BY: dict[str, tuple[Optional[str], Optional[type], tuple[str, ...]]] = {
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
    # No field of its own, and that is the honest entry rather than a gap. A
    # rename is not drawn: it is *applied*, by `decisions()` reporting a
    # judgment under the package's current name. What a client sees is the
    # judgment having moved, plus `orphans` shrinking by one. The response to
    # the rename route carries the edge itself.
    "same_as": (None, ClassificationOut, ("subject", "claim")),
    # A field, but no item model and no edge on it. What a client reads is a
    # *rank* -- `order`, floor first -- rather than the pairs somebody stated,
    # because a renderer needs a height and a reader needs to know which of two
    # packages is lower without walking edges. Sending the pairs as well would
    # be sending the same fact twice, in a form nothing consumes.
    "above": ("order", None, ()),
}
"""How each declared relation reaches a client, if it does.

Relation -> the field on ``ModelOut`` or ``None`` where the relation is applied
rather than listed, the model carrying it, and the fields that carry the edge.
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
            if on_model is not None:
                assert on_model in ModelOut.model_fields, f"{name}: ModelOut.{on_model}"
            if item is not None:
                for field in fields:
                    assert field in item.model_fields, f"{name}: {item.__name__}.{field}"

    def test_a_judgment_that_lands_nowhere_is_still_reported(self) -> None:
        """The counterpart to ``same_as`` having no field of its own.

        A rename is how a judgment finds its way home; ``orphans`` is what the
        model says while it has not. Without that field a decision about a
        renamed package stands in the log, joins to no proposal, and disappears
        from every surface -- true, unactionable, and invisible, which is the
        worst of the three states it could be in.
        """
        assert "orphans" in ModelOut.model_fields
        for field in ("subject", "claim", "verdict"):
            assert field in OrphanOut.model_fields

    def test_the_order_is_carried_as_a_rank_and_not_as_pairs(self) -> None:
        """``above`` is the one relation whose field holds no edges.

        Every other entry above names the fields that carry a src and a dst.
        This one carries neither: `order` is the layers ranked floor-first, and
        the pairs that produced it stay in the log. A client that needed the
        pairs would be re-deriving the rank the server already computed, chain
        following and cycle breaking included.
        """
        assert "order" in ModelOut.model_fields
        _on_model, item, fields = CARRIED_BY["above"]
        assert (item, fields) == (None, ())
