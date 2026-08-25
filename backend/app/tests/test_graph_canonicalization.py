"""What the catalogue does to a claim between the model saying it and it landing.

The three steps ADR 0007 put in the validator rather than the prompt, because the
prompt had already asked and been ignored. Every case here is drawn from a
relation the live graph actually contains.

Pure — no database, no model, no fixtures.
"""

from bacteria.app.graph.extraction import _clean

PERSON = {"label": "Diane", "kind": "person"}
ACME = {"label": "Acme", "kind": "organization"}
SELF = {"label": "self", "kind": "person"}


def claim(src, rel, dst, tense="current"):
    return {"src": src, "rel": rel, "dst": dst, "tense": tense, "reason": "they said so"}


def test_a_converse_alias_arrives_the_right_way_round():
    """``self —mother_of→ Guillermo`` is in the live graph and reads backwards.

    Canonicalizing without swapping would file it under an approved relation,
    where nothing downstream can tell it from a correct claim. This is the case
    the whole converse flag exists for.
    """
    cleaned = _clean(claim(SELF, "mother_of", PERSON))

    assert cleaned is not None
    assert cleaned["rel"] == "mother"
    assert cleaned["src"] == PERSON, "the ends swap: Diane's mother is the owner"
    assert cleaned["dst"] == SELF


def test_a_plain_alias_is_rewritten_without_swapping():
    cleaned = _clean(claim(PERSON, "works_for", ACME))

    assert cleaned is not None
    assert cleaned["rel"] == "employer"
    assert cleaned["src"] == PERSON


def test_the_word_the_model_chose_survives_the_rewrite():
    """What makes collapsing two relation names the *cheap* direction.

    Merging two nodes is unrecoverable because their assertions interleave under
    one id. Merging two relation names is not, but only because the original is
    still here: a wrong alias is undone by re-reading the log.
    """
    cleaned = _clean(claim(PERSON, "works_for", ACME))

    assert cleaned is not None
    assert cleaned["proposed_rel"] == "works_for"


def test_a_claim_already_canonical_carries_no_proposed_relation():
    cleaned = _clean(claim(PERSON, "employer", ACME))

    assert cleaned is not None
    assert "proposed_rel" not in cleaned


def test_an_inverted_claim_is_flipped_when_the_kinds_say_so():
    """``employer`` is person → organization, so backwards is detectable."""
    cleaned = _clean(claim(ACME, "employer", PERSON))

    assert cleaned is not None
    assert cleaned["src"] == PERSON
    assert cleaned["dst"] == ACME


def test_a_claim_that_fits_no_way_round_is_dropped():
    """Two organizations cannot be an ``employer`` claim in either direction."""
    other = {"label": "Globex", "kind": "organization"}

    assert _clean(claim(ACME, "employer", other)) is None


def test_a_symmetric_signature_catches_nothing_and_that_is_the_honest_result():
    """``mother`` is person → person, so an inversion passes straight through.

    Recorded as a test because it is a limit rather than a bug: the reading
    sentence in the prompt is the prevention here, and human review is the
    backstop. A test asserting otherwise would be claiming a check that does not
    exist.
    """
    cleaned = _clean(claim(SELF, "mother", PERSON))

    assert cleaned is not None
    assert cleaned["src"] == SELF, "nothing here can tell this from the truth"


def test_a_name_claim_is_dropped_rather_than_recorded():
    """Five of the first fifteen real rows were this, under five spellings.

    ``self —name→ Guillermo`` makes "Guillermo" a node, so the graph holds the
    same human twice. Dropping loses a real fact and is the recoverable
    direction; the fact belongs in the owner node's label and there is no write
    path for one.
    """
    for rel in ("name", "called", "alternative_name", "nickname"):
        assert _clean(claim(SELF, rel, PERSON)) is None, rel


def test_a_relation_the_catalogue_does_not_know_is_kept_as_it_came():
    """The tail. Not an error, and the evidence for what the catalogue lacks."""
    cleaned = _clean(claim(SELF, "pet", {"label": "Canija", "kind": "person"}))

    assert cleaned is not None
    assert cleaned["rel"] == "pet"
    assert "proposed_rel" not in cleaned


def test_the_tail_is_not_kind_checked():
    """There is no signature to check it against, so nothing is enforced."""
    cleaned = _clean(claim(ACME, "interlocutor", ACME | {"label": "Globex"}))

    assert cleaned is not None
    assert cleaned["rel"] == "interlocutor"
