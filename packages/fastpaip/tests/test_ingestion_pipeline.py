"""Tests for the pipeline's logic, with no database in sight.

`build_pipeline` takes its persist step as an argument precisely so this is
possible: what the steps decide is separable from where the results go, and
these tests exercise the first without the second.
"""

from fastpaip.ingestion.pipeline import Batch, build_pipeline


async def run(records, persist=None) -> Batch:
    calls = []

    async def _persist(batch: Batch) -> Batch:
        calls.append(batch)
        batch.batch_id = 1
        return batch

    pipeline = build_pipeline(persist=persist or _persist)
    batch = await pipeline.handle(Batch(source="test", raw=records))
    batch.persist_calls = calls  # type: ignore[attr-defined]
    return batch


async def test_every_record_ends_up_accepted_or_rejected():
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

    batch = await run(records)

    assert len(batch.accepted) + len(batch.rejected) == len(records)


async def test_a_rejection_carries_a_usable_reason():
    batch = await run([{"name": "no id"}])

    assert "external_id" in batch.rejected[0].reason


async def test_duplicate_ids_within_a_batch_are_rejected_not_merged():
    """Two records claiming the same id cannot both be right.

    Merging or last-one-wins would silently discard data the caller sent; the
    rejection makes the collision the caller's to resolve.
    """
    batch = await run([{"external_id": "1", "name": "A"}, {"external_id": "1", "name": "B"}])

    assert len(batch.accepted) == 1
    assert "duplicate" in batch.rejected[0].reason


async def test_a_rejection_quotes_the_record_as_it_arrived():
    """Normalization must not rewrite the evidence.

    A caller shown a cleaned-up version of what they sent has to guess what was
    wrong with the original, which is the one thing the reason exists to remove.
    """
    batch = await run([{"external_id": "  ", "name": "  Ada  "}])

    assert batch.rejected[0].payload["name"] == "  Ada  "


async def test_the_two_required_fields_are_normalized():
    batch = await run([{"external_id": " 1 ", "name": " Ada "}])

    stored = batch.accepted[0]
    assert stored["external_id"] == "1"
    assert stored["name"] == "Ada"


async def test_every_other_field_is_passed_through_untouched():
    """The pipeline does not know what a record represents, and must not act as if.

    Guards against a domain assumption creeping back in. `email` used to be
    lowercased here — inherited from a leftover model rather than chosen — which
    made the behaviour inconsistent rather than absent: a caller whose field was
    `contact_email` got nothing, and no rule could be stated about which fields
    were cleaned.
    """
    batch = await run(
        [
            {
                "external_id": "1",
                "name": "Ada",
                "email": " ADA@Example.COM ",
                "contact_email": " OTHER@x.io ",
                "seats": 12,
                "tags": ["vip"],
            }
        ]
    )

    stored = batch.accepted[0]
    assert stored["email"] == " ADA@Example.COM "
    assert stored["contact_email"] == " OTHER@x.io "
    assert stored["seats"] == 12
    assert stored["tags"] == ["vip"]


async def test_normalization_does_not_invent_fields():
    """A record keeps exactly the keys it arrived with.

    Adding an absent field as an empty string would turn "not provided" into
    "provided as blank", which are different facts stored as different rows.
    """
    batch = await run([{"external_id": "1", "name": "Ada"}])

    assert set(batch.accepted[0]) == {"external_id", "name"}


async def test_persist_still_runs_when_every_record_was_rejected():
    """A batch that failed entirely is the one whose evidence matters most.

    Gating the persist step on `accepted` alone looks right and throws away
    exactly the records someone will later need to explain — reporting the
    reasons in the response and keeping none of them.
    """
    batch = await run([{"name": "invalid"}])

    assert len(batch.persist_calls) == 1
    assert batch.batch_id is not None


async def test_persist_is_skipped_for_an_entirely_empty_batch():
    """The step declines rather than the caller branching around it.

    Nothing accepted and nothing rejected means nothing happened, and a batch
    row would imply a submission that never came.
    """
    batch = await run([])

    assert batch.persist_calls == []
    assert batch.batch_id is None


async def test_rejections_survive_a_failing_persist_step():
    """Evidence gathered before a failure is still on the batch afterwards.

    The steps mutate the batch in place for this reason: a caller handling the
    exception can still see which records were rejected and why, rather than
    losing the whole diagnosis with the run.
    """
    async def boom(_batch):
        raise RuntimeError("database gone")

    batch = Batch(source="test", raw=[{"external_id": "1", "name": "A"}, {"name": "bad"}])
    pipeline = build_pipeline(persist=boom)

    try:
        await pipeline.handle(batch)
    except RuntimeError:
        pass

    assert len(batch.rejected) == 1
    assert len(batch.accepted) == 1


async def test_a_null_required_field_is_rejected_not_stringified():
    """JSON null must be absent, not the four-character word.

    `str(None)` is "None", which is non-blank, so a null id passed validation
    and was stored under the literal id "None" -- where every other null-id
    record would collide with it, and so would anything genuinely called that.
    """
    batch = await run([{"external_id": None, "name": "null id"}])

    assert batch.accepted == []
    assert "external_id" in batch.rejected[0].reason


async def test_a_zero_external_id_is_still_valid():
    """0 is a real identifier, and a falsy check would throw it away.

    The obvious fix for null -- `record.get(f) or ""` -- rejects this, which is
    why the check tests for None explicitly rather than for truthiness.
    """
    batch = await run([{"external_id": 0, "name": "zero"}])

    assert batch.rejected == []
    assert batch.accepted[0]["external_id"] == "0"


async def test_a_rejection_carries_its_position_in_the_submission():
    """Two identical bad records must be distinguishable.

    Without an index a caller correlates rejections by payload equality, and
    identical records collapse into one indistinguishable pair — so "which of
    the ones I sent failed" has no answer. Every comparable API (Elasticsearch
    bulk, BigQuery insertAll, SQS partial batch response) reports position or
    id for exactly this reason.
    """
    batch = await run(
        [
            {"external_id": "1", "name": "fine"},
            {"name": "identical"},
            {"external_id": "2", "name": "also fine"},
            {"name": "identical"},
        ]
    )

    assert [r.index for r in batch.rejected] == [1, 3]
    assert batch.rejected[0].payload == batch.rejected[1].payload


async def test_the_index_counts_every_submitted_record_not_only_the_rejected():
    """Positions refer to what the caller sent, not to the rejection list.

    An index counted over rejections alone would be a second numbering the
    caller has no way to reconstruct, and would point at the wrong record.
    """
    batch = await run(
        [
            {"name": "bad"},
            {"external_id": "1", "name": "good"},
            {"external_id": "2", "name": "good"},
            {"name": "bad"},
        ]
    )

    assert [r.index for r in batch.rejected] == [0, 3]
