"""Tests for the chain: ordering, skipping, and per-instance links."""

from dataclasses import dataclass, field

from bacteria.app.core.adapters import FunctionalProcessor
from bacteria.app.core.handlers import StepHandler


@dataclass
class Doc:
    """Data threaded through a chain, recording which steps touched it."""

    text: str = ""
    seen: list[str] = field(default_factory=list)


def step(name: str, applies=lambda _doc: True) -> StepHandler:
    def process(doc: Doc) -> Doc:
        doc.seen.append(name)
        return doc

    return StepHandler(FunctionalProcessor(can_handle=applies, process=process))


async def test_steps_run_in_the_order_they_were_linked():
    first, second, third = step("a"), step("b"), step("c")
    first.set_next(second).set_next(third)

    result = await first.handle(Doc())

    assert result.seen == ["a", "b", "c"]


async def test_set_next_returns_the_new_link_so_chains_read_forwards():
    """`a.set_next(b).set_next(c)` must build a→b→c, not a→c.

    Returning `self` instead would make the same expression silently build the
    chain backwards — the fluent call still reads left to right, so the mistake
    is invisible at the call site.
    """
    first, second, third = step("a"), step("b"), step("c")

    assert first.set_next(second) is second
    assert second.set_next(third) is third


async def test_a_declining_step_is_skipped_but_the_chain_continues():
    """can_handle False must skip that step only, not end the pipeline.

    Ending the chain would make one step's decision silently discard every step
    after it, and the result would simply be wrong with nothing to point at.
    """
    chain = step("a")
    chain.set_next(step("b", applies=lambda _doc: False)).set_next(step("c"))

    result = await chain.handle(Doc())

    assert result.seen == ["a", "c"]


async def test_handlers_do_not_share_a_successor():
    """Each handler's link is its own.

    `_next_handler` was declared as a class attribute. It appeared to work,
    because `set_next` assigns to the instance and shadows it — but every
    handler that had not yet been given a successor read one shared default,
    and anything inspecting the link before `set_next` saw the class's value
    rather than that instance's.
    """
    linked, unlinked = step("a"), step("z")
    linked.set_next(step("b"))

    assert linked._next_handler is not None
    assert unlinked._next_handler is None


async def test_a_single_handler_returns_its_data_unchanged_through_the_tail():
    """The last link returns the data rather than None.

    A chain's tail is the easiest place to drop the payload, and a caller that
    receives None gets a failure far from the cause.
    """
    result = await step("only").handle(Doc(text="payload"))

    assert result.text == "payload"
    assert result.seen == ["only"]


async def test_a_coroutine_step_is_awaited_not_returned_unrun():
    """An async step must run, not be handed back as a coroutine.

    A coroutine object is truthy and passes silently down the chain, so the
    pipeline reports success while that step never executed and every later step
    operated on the wrong data.
    """

    async def process(doc: Doc) -> Doc:
        doc.seen.append("async")
        return doc

    handler = StepHandler(FunctionalProcessor(can_handle=lambda _doc: True, process=process))

    result = await handler.handle(Doc())

    assert result.seen == ["async"]


async def test_a_coroutine_can_handle_is_awaited():
    """A gate that is a coroutine must be resolved before it is believed.

    An un-awaited coroutine is truthy, so a declining async gate would run every
    step it meant to skip.
    """

    async def declines(_doc: Doc) -> bool:
        return False

    ran = []
    handler = StepHandler(
        FunctionalProcessor(can_handle=declines, process=lambda doc: ran.append(1) or doc)
    )

    await handler.handle(Doc())

    assert ran == []
