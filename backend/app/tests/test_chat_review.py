"""The review workflow, tested where it lives rather than where it is printed.

These behaviours used to sit in ``entrypoints/cli.py``, which is omitted from
coverage on the grounds that it holds configuration and no decisions. That
omission is only honest while it is true, and it had stopped being true: the
exception ordering below is a correctness detail that fails silently, and it was
in a file nothing measured.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.store import SESSION_SCOPE, USER_SCOPE
from bacteria.app.chat import review
from bacteria.app.chat.repository import SqlSessionRepository


@pytest.fixture(name="repo")
async def _repo(engine):
    async with AsyncSession(engine) as db:
        yield SqlSessionRepository(db)


@pytest.fixture(name="session_id")
async def _session_id(repo):
    session = await repo.create_session("owner-1")
    return session.session_id


# --- Parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("/proposals", review.ListPending()),
        ("/review", review.ReviewEach()),
        ("/help", review.ShowHelp()),
        ("/accept model tone", review.AcceptOne("model", "tone", SESSION_SCOPE)),
        ("/accept model tone user", review.AcceptOne("model", "tone", USER_SCOPE)),
        ("/reject model tone", review.DiscardOne("model", "tone")),
        ("hello there", review.SendMessage("hello there")),
    ],
)
def test_a_line_is_read_as_the_thing_it_names(line, expected):
    assert review.parse_console_line(line) == expected


@pytest.mark.parametrize(
    "line",
    ["/acccept model tone", "/proposals extra", "/accept model", "/reject model", "/nope"],
)
def test_a_command_that_does_not_parse_asks_for_help_rather_than_reaching_the_model(line):
    """A mistyped command must never be forwarded as conversation.

    Nobody types ``/acccept`` meaning to say it out loud. Sending it would spend
    a turn and a model call on a typo, and the reply would be a model politely
    discussing a command that does not exist.
    """
    assert isinstance(review.parse_console_line(line), review.ShowHelp)


def test_an_unknown_scope_is_refused_rather_than_defaulted():
    """A misspelt scope must not quietly become the narrow one.

    ``/accept model tone usr`` asking for user scope and silently getting
    session scope is the failure that looks like it worked: the memory exists,
    the operator believes it will carry into later conversations, and it will
    not.
    """
    result = review.parse_console_line("/accept model tone usr")

    assert isinstance(result, review.ShowHelp)
    assert "scope" in result.detail


def test_a_doubled_slash_sends_one_slash():
    """The escape, so a message that begins with a slash is still sendable.

    Without it this is the only thing a user can type that the console refuses
    to relay, with no way to insist.
    """
    assert review.parse_console_line("//proposals") == review.SendMessage("/proposals")


# --- Deciding one at a time --------------------------------------------------


@pytest.mark.parametrize(
    ("keystroke", "expected"),
    [
        ("y", review.AcceptThis(SESSION_SCOPE)),
        ("u", review.AcceptThis(USER_SCOPE)),
        ("n", review.RejectThis()),
        ("s", review.SkipThis()),
        ("q", review.StopReview()),
        ("  Y  ", review.AcceptThis(SESSION_SCOPE)),
    ],
)
def test_a_keystroke_means_what_the_walk_offers(keystroke, expected):
    """Every advertised key does the thing it is labelled with.

    ``y`` and ``u`` differ only in blast radius, and confusing them is not
    visible afterwards: both produce a memory that exists and looks right, but
    one of them applies to every later conversation that person has.
    """
    assert review.parse_review_key(keystroke) == expected


def test_an_empty_line_skips_rather_than_rejecting():
    """Pressing enter must never discard a proposal.

    The reflex at a prompt is to hit enter, and rejection is the one answer here
    that cannot be undone -- the proposal is gone and the turn that produced it
    will not come round again. Skipping leaves the same decision available a
    moment later.
    """
    assert review.parse_review_key("") == review.SkipThis()


def test_an_unrecognized_key_is_not_a_skip():
    """A fumbled key asks again instead of advancing.

    If this returned ``SkipThis`` the walk would move past the proposal silently,
    and the person would learn they had missed the one they meant to accept only
    when it was still waiting at the end.
    """
    assert review.parse_review_key("x") == review.Unclear()


def test_the_replacement_note_counts_decisions_made_since_the_listing():
    """A walk must not tell you nothing will be replaced while something will.

    Two proposers finding the same fact is the ordinary case -- ADR 0017 expects
    it, and it is why proposals are keyed by (source, key). So the second entry
    in a walk is routinely a second suggestion for a key the first just
    activated, and the listing that walk is iterating was taken before either
    decision. Shown that snapshot, the reviewer is told the choice is free at
    exactly the moment it is not.
    """
    entry = review.PendingEntry(source="model", key="dog_name", value="v", reason="r")
    just_accepted = review.Held(USER_SCOPE, "Pipin")

    assert review.held_now(entry, {}) == ()
    assert review.held_now(entry, {"dog_name": just_accepted}) == (just_accepted,)
    assert review.held_now(entry, {"other": just_accepted}) == ()


def test_a_scope_already_held_is_not_reported_twice():
    """Accepting into a scope the key already holds is still one replacement."""
    held = review.Held(SESSION_SCOPE, "terse")
    entry = review.PendingEntry(source="model", key="tone", value="v", reason="r", held_by=(held,))

    assert review.held_now(entry, {"tone": review.Held(SESSION_SCOPE, "terse")}) == (held,)
    assert review.held_now(entry, {"tone": review.Held(USER_SCOPE, "chatty")}) == (
        held,
        review.Held(USER_SCOPE, "chatty"),
    )


def test_the_note_names_the_value_a_decision_would_destroy():
    """Warning that something will be replaced, without saying what, cost a value.

    Live: the extractor's `dad_name = "Pedro"` was accepted at user scope, and
    two entries later the model's `dad_name = "Your dad's name is Pedro."` was
    accepted over it -- a worse phrasing of the same fact, promoted because the
    note said only that a replacement would happen. Overwriting is destructive
    and there is no history table, so the good value was unrecoverable the
    instant the second keystroke landed.
    """
    entry = review.PendingEntry(
        source="model",
        key="dad_name",
        value="Your dad's name is Pedro.",
        reason="r",
        held_by=(review.Held(USER_SCOPE, "Pedro"),),
    )

    assert review.held_now(entry, {})[0].value == "Pedro"


def test_a_walks_own_decision_supersedes_the_listings_value():
    """The newer of two values is the one the walk just wrote, not the snapshot.

    Accepting twice into one scope during a walk is how a reviewer works through
    competing suggestions for a key. Showing the value the listing recorded would
    name something already overwritten -- a note that is stale in its value while
    being right about its scope, which is the harder version of the bug this
    tracking exists to prevent.
    """
    entry = review.PendingEntry(
        source="model",
        key="tone",
        value="chatty",
        reason="r",
        held_by=(review.Held(USER_SCOPE, "stale"),),
    )

    assert review.held_now(entry, {"tone": review.Held(USER_SCOPE, "terse")}) == (
        review.Held(USER_SCOPE, "terse"),
    )


# --- Operations --------------------------------------------------------------


async def test_a_listing_names_the_scopes_a_key_already_holds(repo, session_id):
    """Accepting replaces rather than joins, and that must be visible first.

    Proposals are keyed by (source, key) and active memory by key alone, so a
    second suggestion for a key overwrites the first. A reviewer choosing
    between two phrasings of one fact needs to know that is the choice, and
    needs the phrasing they would be discarding in order to make it.
    """
    await repo.remember(session_id, key="tone", value="terse", reason="r", scope=USER_SCOPE)
    await repo.propose(session_id, key="tone", value="chatty", reason="r", source="model")
    await repo.propose(session_id, key="unrelated", value="v", reason="r", source="model")

    result = await review.pending(repo, session_id)

    assert isinstance(result, review.Pending)
    by_key = {entry.key: entry for entry in result.entries}
    assert by_key["tone"].held_by == (review.Held(USER_SCOPE, "terse"),)
    assert by_key["unrelated"].held_by == ()


async def test_an_unknown_session_is_not_reported_as_a_missing_proposal(repo):
    """The ordering that fails silently: UnknownSessionError subclasses KeyError.

    Catch them the other way round and a session that does not exist is
    reported as "no such proposal", which sends whoever is debugging to look for
    a suggestion in a conversation that was never there.
    """
    result = await review.accept(repo, "no-such-session", source="model", key="tone")

    assert isinstance(result, review.NoSuchSession)


async def test_a_missing_proposal_is_reported_as_one(repo, session_id):
    result = await review.accept(repo, session_id, source="model", key="never-proposed")

    assert isinstance(result, review.NoSuchProposal)


async def test_accepting_activates_at_the_scope_asked_for(repo, session_id):
    """The scope is the human's choice and must survive the trip.

    Defaulting it here would decide, on someone's behalf, that a fact applies to
    every future conversation they have -- the escalation the agent's ADR 0021
    reserves for the person confirming.
    """
    await repo.propose(session_id, key="tone", value="terse", reason="r", source="model")

    result = await review.accept(repo, session_id, "model", "tone", USER_SCOPE)

    assert isinstance(result, review.Accepted)
    assert result.scope == USER_SCOPE
    state = await repo.get_state(session_id)
    assert state.user_memory["tone"].value == "terse"
    assert "tone" not in state.memory
    assert state.proposals == {}


async def test_discarding_says_whether_there_was_anything_there(repo, session_id):
    """Rejection is idempotent, and the caller is still told which case it was.

    Making an absent proposal an error would break the idempotence the store
    promises; saying nothing would leave an operator who mistyped a key
    believing they discarded something.
    """
    await repo.propose(session_id, key="tone", value="terse", reason="r", source="model")

    first = await review.discard(repo, session_id, "model", "tone")
    second = await review.discard(repo, session_id, "model", "tone")

    assert isinstance(first, review.Discarded) and first.present
    assert isinstance(second, review.Discarded) and not second.present
