"""Asking a model about a codebase, with a fake model.

No provider is called. What is worth testing here is not what a model says — it
is what it is *allowed* to do and *shown*, and both are decidable without one:
that the gate refuses anything outside the read-only set, that the tools answer
from the parse rather than from a name, and that an unratified proposal is never
reported as settled.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from bacteria.agent.model.protocol import ModelResponse
from bacteria.app.architecture.conversation import ASKED, PREAMBLE, OnlyReads, ask, registry_for
from bacteria.app.architecture.models import Project
from bacteria.app.architecture.service import Model, model_of
from bacteria.app.architecture.tools import (
    READ_ONLY,
    build_describe_package_tool,
    build_list_boundaries_tool,
    build_list_proposals_tool,
)

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(name="model", scope="module")
def _model() -> Model:
    """This repository, parsed once for the whole file.

    Real rather than synthetic: the tools exist to answer about an actual tree,
    and a hand-built one would not have caught that `describe_package` matched
    a prefix rather than a package.
    """
    from datetime import datetime, timezone

    project = Project(
        project_id="p1",
        principal_id="tester",
        name="bacteria",
        location=str(REPO),
        test_command=None,
        added_at=datetime.now(timezone.utc),
    )
    return model_of(project)


class Replies:
    """A model that says one thing and never calls a tool."""

    def __init__(self, text: str = "understood") -> None:
        self.text = text
        self.seen: list[Any] = []

    async def send(self, *args: Any, **kwargs: Any) -> ModelResponse:
        self.seen.append((args, kwargs))
        return ModelResponse(text=self.text, tool_calls=[], stop_reason="end_turn", raw={})


class TestTheGate:
    def test_a_read_only_tool_is_allowed(self) -> None:
        gate = OnlyReads()

        assert gate({"id": "1", "name": "describe_package", "input": {}}) is True
        assert gate.allowed == ["describe_package"]

    def test_anything_else_is_refused(self) -> None:
        """Default-deny, which is the whole value.

        ``chat/service.py`` says a second tool means writing a real gate first,
        and an allowlist is the only kind that refuses a tool registered later
        by somebody who did not read that. A denylist of the things somebody
        thought of fails open.
        """
        gate = OnlyReads()

        assert gate({"id": "1", "name": "remember", "input": {}}) is False
        assert gate({"id": "2", "name": "run_tests", "input": {}}) is False
        assert gate.refused == ["remember", "run_tests"]

    def test_the_registry_offers_only_what_the_gate_allows(self, model: Model) -> None:
        """The two lists have to agree, and they are written in two files.

        A tool offered but refused wastes a turn and reads to the model as a
        malfunction; one allowed but never offered is a hole nobody notices.
        """
        offered = {schema["name"] for schema in registry_for(model).schemas_for_run()}

        assert offered == set(READ_ONLY)


class TestWhatTheToolsAnswer:
    def test_describe_answers_from_the_parse(self, model: Model) -> None:
        """The point of the tool: a real dependency, not a plausible one.

        A model asked what ``graph`` depends on will answer confidently from
        every codebase it has read. This one answers from this one — and the
        answer changed under this test, which is the point being made twice.
        It asserted a dependency on ``core`` until the personal domain got its
        own package and took the substrate's only route there with it. A model
        answering from memory would still be saying ``core``.
        """
        tool = build_describe_package_tool(model)
        answer = json.loads(tool.handler({"name": "bacteria.app.graph"}))

        assert answer["package"] == "bacteria.app.graph"
        assert answer["modules"]["count"] > 5
        assert "graph_assertion" in answer["tables"]
        # Nothing. The substrate imports no other package in this repository,
        # which is what makes it one, and is checked here rather than asserted
        # in prose somewhere.
        assert answer["depends_on"]["names"] == []
        assert any(d.startswith("bacteria.app.personal") for d in answer["depended_on_by"]["names"])

    def test_an_unknown_name_is_said_rather_than_returned_empty(self, model: Model) -> None:
        """A model handed ``{}`` assumes failure and retries a variation.

        Told the name is unknown, it asks the person or tries a different one.
        """
        tool = build_describe_package_tool(model)
        answer = json.loads(tool.handler({"name": "nothing.like.this"}))

        assert "error" in answer

    def test_an_open_proposal_is_never_reported_as_settled(self, model: Model) -> None:
        """The distinction the whole feature exists to hold.

        A tool that returned ``chat is a feature`` for an unratified proposal
        would put the classifier's guess into the model's mouth as fact — and
        the model would repeat it to the reader as one.
        """
        tool = build_list_proposals_tool(model)
        answer = json.loads(tool.handler({}))

        assert answer["proposals"]
        assert all(p["status"] in ("open", "agreed", "disagreed") for p in answer["proposals"])
        assert "not facts" in answer["note"]

    def test_undecidable_boundaries_reach_the_model(self, model: Model) -> None:
        """A list of passes and failures implies everything was checked.

        Four of this codebase's boundaries were never asked, and a model told
        only about the others would report a clean bill of health.
        """
        tool = build_list_boundaries_tool(model)
        answer = json.loads(tool.handler({}))

        assert answer["cannot_be_decided_from_imports"]
        assert all(b["checked_by"] for b in answer["cannot_be_decided_from_imports"])


class TestAsking:
    async def test_the_question_reaches_the_model_with_its_instructions(self, model: Model) -> None:
        """The preamble is what keeps three kinds of statement apart.

        Without it a model reports a proposal and an import in the same voice,
        which is the confusion every other part of this surface spends its
        design preventing.
        """
        client = Replies("nine modules")

        answer = await ask(client, model, "how big is graph?")

        assert answer.reply == "nine modules"
        assert client.seen, "the model was never called"

    async def test_a_reply_with_no_text_says_so(self, model: Model) -> None:
        """``text`` is ``None`` when a model replied with tool calls only.

        A real outcome rather than an error — but an empty bubble reads as a
        failure, and a reader cannot tell one from the other.
        """
        client = Replies("")
        client.text = ""

        answer = await ask(client, model, "anything")

        assert "said nothing" in answer.reply

    def test_the_preamble_names_all_three_kinds_of_statement(self) -> None:
        """Guarded because it is prose, and prose is what silently drifts."""
        for phrase in ("Derived facts", "Stated boundaries", "Proposals"):
            assert phrase in PREAMBLE
        assert ASKED.strip().endswith("asks:")
