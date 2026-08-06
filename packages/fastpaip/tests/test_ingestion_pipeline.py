"""Tests for the pipeline's logic, with no database in sight.

`build_pipeline` takes its persist step as an argument precisely so this is
possible: what the steps decide is separable from where the results go, and
these tests exercise the first without the second.
"""

from fastpaip.ingestion.pipeline import Batch, build_pipeline


def run(records, persist=None) -> Batch:
    calls = []

    def _persist(batch: Batch) -> Batch:
        calls.append(batch)
        batch.batch_id = 1
        return batch

    pipeline = build_pipeline(persist=persist or _persist)
    batch = pipeline.handle(Batch(source="test", raw=records))
    batch.persist_calls = calls  # type: ignore[attr-defined]
    return batch


def test_every_record_ends_up_accepted_or_rejected():
    """The two lists must account for the whole submission.

    This is what lets a caller reconcile what it sent against what happened, and
    it is the property most easily lost by a `continue` landing in the wrong
    branch — the record then vanishes from both lists and from the response.
    """
    records = [
        {"external_id": "1", "name": "Ada"},
        {"name": "no id"},
        {"external_id": "2", "name": ""},
        {"external_id": "3", "name": "Grace"},
    ]

    batch = run(records)

    assert len(batch.accepted) + len(batch.rejected) == len(records)


def test_a_rejection_carries_a_usable_reason():
    batch = run([{"name": "no id"}])

    assert "external_id" in batch.rejected[0].reason


def test_duplicate_ids_within_a_batch_are_rejected_not_merged():
    """Two records claiming the same id cannot both be right.

    Merging or last-one-wins would silently discard data the caller sent; the
    rejection makes the collision the caller's to resolve.
    """
    batch = run([{"external_id": "1", "name": "A"}, {"external_id": "1", "name": "B"}])

    assert len(batch.accepted) == 1
    assert "duplicate" in batch.rejected[0].reason


def test_a_rejection_quotes_the_record_as_it_arrived():
    """Normalization must not rewrite the evidence.

    A caller shown a cleaned-up version of what they sent has to guess what was
    wrong with the original, which is the one thing the reason exists to remove.
    """
    batch = run([{"external_id": "  ", "name": "  Ada  "}])

    assert batch.rejected[0].payload["name"] == "  Ada  "


def test_accepted_records_are_normalized():
    batch = run([{"external_id": " 1 ", "name": " Ada ", "email": " ADA@Example.COM "}])

    stored = batch.accepted[0]
    assert stored["external_id"] == "1"
    assert stored["name"] == "Ada"
    assert stored["email"] == "ada@example.com"


def test_a_record_without_an_email_stays_without_one():
    """Normalization must not invent fields.

    Adding an empty string would turn "not provided" into "provided as blank",
    which are different facts and are stored as different rows.
    """
    batch = run([{"external_id": "1", "name": "Ada"}])

    assert "email" not in batch.accepted[0]


def test_persist_still_runs_when_every_record_was_rejected():
    """A batch that failed entirely is the one whose evidence matters most.

    Gating the persist step on `accepted` alone looks right and throws away
    exactly the records someone will later need to explain — reporting the
    reasons in the response and keeping none of them.
    """
    batch = run([{"name": "invalid"}])

    assert len(batch.persist_calls) == 1
    assert batch.batch_id is not None


def test_persist_is_skipped_for_an_entirely_empty_batch():
    """The step declines rather than the caller branching around it.

    Nothing accepted and nothing rejected means nothing happened, and a batch
    row would imply a submission that never came.
    """
    batch = run([])

    assert batch.persist_calls == []
    assert batch.batch_id is None


def test_rejections_survive_a_failing_persist_step():
    """Evidence gathered before a failure is still on the batch afterwards.

    The steps mutate the batch in place for this reason: a caller handling the
    exception can still see which records were rejected and why, rather than
    losing the whole diagnosis with the run.
    """
    def boom(_batch):
        raise RuntimeError("database gone")

    batch = Batch(source="test", raw=[{"external_id": "1", "name": "A"}, {"name": "bad"}])
    pipeline = build_pipeline(persist=boom)

    try:
        pipeline.handle(batch)
    except RuntimeError:
        pass

    assert len(batch.rejected) == 1
    assert len(batch.accepted) == 1
