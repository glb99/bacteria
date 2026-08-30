"""The personal domain's vocabulary, and what is easy to get wrong about it.

A converse alias applied without swapping the ends produces a *confidently
backwards* edge — worse than the ungoverned name it replaced, because it now
looks like approved vocabulary. And canonicality has to stay a question about the
catalogue rather than about a row, or promoting a relation becomes a migration.

Pure — no database, no fixtures.
"""

from bacteria.app.graph.catalogue import promotable
from bacteria.app.personal.catalogue import CATALOGUE, VOCABULARY


def test_a_converse_alias_reports_that_the_ends_must_swap():
    """``mother_of`` is the opposite of ``mother``, not another word for it.

    The live graph contains ``self —mother_of→ Guillermo``, which reads as the
    owner being someone's mother when the owner *is* Guillermo. Canonicalizing
    that without swapping would file a backwards claim under an approved
    relation, where nothing downstream can tell it from a correct one.
    """
    resolution = VOCABULARY.resolve("mother_of")

    assert resolution is not None
    assert resolution.relation.name == "mother"
    assert resolution.swap is True


def test_a_plain_alias_does_not_swap():
    """``works_for`` says the same thing as ``employer`` and in the same order."""
    resolution = VOCABULARY.resolve("works_for")

    assert resolution is not None
    assert resolution.relation.name == "employer"
    assert resolution.swap is False


def test_a_relation_resolves_to_itself_without_swapping():
    resolution = VOCABULARY.resolve("employer")

    assert resolution is not None
    assert resolution.relation.name == "employer"
    assert resolution.swap is False


def test_an_unknown_relation_resolves_to_nothing_rather_than_being_rejected():
    """The tail is not an error, and this is the seam where that is decided.

    ``None`` means the catalogue has nothing to say. The caller records the claim
    under the model's own word, because the tail is the evidence for what the
    catalogue should become.
    """
    assert VOCABULARY.resolve("interlocutor") is None
    assert VOCABULARY.is_canonical("interlocutor") is False


def test_canonicality_is_a_question_about_the_catalogue():
    assert VOCABULARY.is_canonical("employer") is True
    assert VOCABULARY.is_canonical("works_for") is False, "an alias is a spelling, not an entry"


def test_lookup_ignores_aliases():
    """Callers ask about a relation as *recorded*, which is already canonical."""
    assert VOCABULARY.lookup("employer") is not None
    assert VOCABULARY.lookup("works_for") is None


def test_every_functional_relation_can_state_its_rule():
    """A rule a person cannot read is a rule they cannot disagree with.

    The catalogue's sentence says which way round to read a claim; the invariant
    says what cannot be true twice. Only the second is any use to someone being
    shown a contradiction, and folding them into one field is a mistake this
    catches — it was in ADR 0007's sketch and a route test caught it.
    """
    for relation in VOCABULARY.functional():
        assert relation.invariant, f"{relation.name} is functional and states no rule"


def test_only_the_identity_relation_is_withheld_from_the_extractor():
    """If this ever lists a second name, the reason wants stating in the record."""
    withheld = [r.name for r in CATALOGUE if not r.extractable]

    assert withheld == ["same_as"]


def test_a_relation_states_a_rule_only_when_it_has_one():
    for relation in CATALOGUE:
        if not relation.functional:
            assert relation.invariant is None


def test_no_alias_collides_with_a_relation_or_another_alias():
    """Two entries claiming one spelling makes resolution depend on order."""
    seen: set[str] = set()
    for relation in CATALOGUE:
        assert relation.name not in seen
        seen.add(relation.name)
    for relation in CATALOGUE:
        for alias in relation.aliases:
            assert alias.name not in seen, f"{alias.name} is claimed twice"
            seen.add(alias.name)


def test_the_prompt_block_names_every_relation_and_reads_its_direction():
    """What the model is shown is generated, so it cannot drift from the source.

    The previous design wrote the vocabulary beside the prompt and asked the
    model to be consistent with runs it could not see.
    """
    block = VOCABULARY.describe()

    for relation in CATALOGUE:
        if not relation.extractable:
            continue
        assert relation.name in block
        assert relation.sentence in block
    assert "works_for" in block, "a synonym is worth offering"


def test_the_prompt_block_never_offers_a_merge():
    """`same_as` is canonical and must not reach the extractor's vocabulary.

    ADR 0006's asymmetry: splitting one thing across two nodes is recoverable,
    collapsing two into one is not. A model handed `same_as` would be guessing in
    the direction that cannot be undone, one plausible suggestion at a time.
    """
    assert VOCABULARY.is_canonical("same_as")
    assert "same_as" not in VOCABULARY.describe()


def test_the_prompt_block_does_not_advertise_a_converse_alias():
    """Offering ``mother_of`` under "<src>'s mother is <dst>" invites the flip.

    The alias exists to recognize a name the model reaches for unasked, and the
    swap undoes it. Listing it as an alternative spelling would encourage the one
    thing the catalogue is there to prevent.
    """
    block = VOCABULARY.describe()

    assert "mother_of" not in block
    assert "employs" not in block


def test_a_tail_relation_seen_three_times_is_worth_asking_about():
    """The rule of three, deciding when to *ask* and never when to act."""
    candidates = promotable({"pet": 3, "owns": 1}, VOCABULARY)

    assert [c.name for c in candidates] == ["pet"]
    assert candidates[0].count == 3


def test_a_canonical_relation_is_never_a_candidate():
    """It is already in, so counting it says nothing anyone can act on."""
    assert promotable({"employer": 99}, VOCABULARY) == []


def test_candidates_lead_with_the_strongest_case_and_break_ties_by_name():
    """Two runs over unchanged data must print the same thing, or a diff lies."""
    candidates = promotable({"pet": 4, "owns": 9, "knows": 4}, VOCABULARY)

    assert [c.name for c in candidates] == ["owns", "knows", "pet"]
