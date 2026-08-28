"""What a model may ask about a codebase, and nothing it may do to one.

**Every tool here reads.** None writes a row, runs a process, or touches a file
outside the parse the request already performed. That is what makes registering
them defensible at all: ``chat/service.py`` says a second tool means writing a
real gate *first*, and the gate this feature writes is
:class:`~bacteria.app.architecture.conversation.OnlyReads` — an allowlist of
these names, refusing everything else by default rather than allowing everything
by omission.

**They answer from the model, never from the model's memory of Python.** A model
asked *"what depends on graph.temporal"* without a tool will answer plausibly and
wrongly, because it has read a great deal of code that is not this code. Each
tool below closes over one parsed :class:`Model`, so the answer is the tree as it
stands rather than as a language model recalls it.

**And they are constrained by the ontology.** ``describe`` reports a package's
classification only where somebody agreed to one, and says so where nobody has.
A tool that returned "chat is a feature" for an unratified proposal would put the
classifier's guess into the model's mouth as settled fact, which is the whole
distinction this feature exists to hold.

Not built:
    Any tool that changes anything. Agreeing to a classification, retiring a
    boundary and running a suite are all real acts with real records, and the
    approval gate has nobody to ask over HTTP — the request that would answer
    arrives after the one that asked. The model can *recommend* them in prose;
    the person clicks. See bacteria's ADR 0017 and ``chat/service.py``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from bacteria.agent.tools.registry import ToolDefinition
from bacteria.app.architecture.classify import sentence
from bacteria.app.architecture.service import Model

LIMIT = 40
"""How many names one answer may carry.

A package with two hundred dependents is a real answer and an unreadable one,
and a model handed two hundred names will summarise them into a sentence nobody
can check. Truncated answers say how many were left out.
"""


def _listing(names: list[str]) -> dict[str, Any]:
    return {
        "count": len(names),
        "names": sorted(names)[:LIMIT],
        "truncated": max(0, len(names) - LIMIT),
    }


Verdicts = Mapping[tuple[str, str], str]
"""What a person has ruled about each proposal, keyed by ``(subject, claim)``.

Passed in rather than read from the model, because ``model_of`` is a pure parse
and verdicts live in the database. Keeping the parse free of I/O is what lets a
check be tested against a hand-built tree, and it is worth an argument here to
preserve it.

Empty is the ordinary state of a new project: nothing has been ruled, and every
proposal is open.
"""


def build_describe_package_tool(model: Model, verdicts: Verdicts | None = None) -> ToolDefinition:
    """A package: what it holds, what it reaches, and what was said about it."""

    ruled: Verdicts = verdicts or {}

    def handler(tool_input: dict[str, Any]) -> str:
        wanted = str(tool_input.get("name", "")).strip()
        inside = [
            m
            for m in model.derived.modules.values()
            if m.name == wanted or m.name.startswith(wanted + ".")
        ]
        if not inside:
            # Named rather than empty. A model handed `{}` assumes the tool
            # failed and tries a variation; told the name is unknown, it asks
            # the person or tries a different name.
            return json.dumps({"error": f"nothing here is called {wanted!r}"})

        names = {m.name for m in inside}
        out = [i for i in model.derived.imports if i.src in names and i.dst not in names]
        into = [i for i in model.derived.imports if i.dst in names and i.src not in names]
        proposal = next(
            (p for p in model.proposals if p.subject == wanted and p.claim != "role"), None
        )

        return json.dumps(
            {
                "package": wanted,
                "modules": _listing([m.name for m in inside]),
                "tables": sorted({t for m in inside for t in m.tables}),
                "depends_on": _listing(sorted({i.dst for i in out})),
                "depended_on_by": _listing(sorted({i.src for i in into})),
                # Three states, never two. A proposal nobody has ruled on is not
                # a fact about this codebase, and reporting it as one would put
                # the classifier's guess into the model's mouth as settled.
                "classification": (
                    None
                    if proposal is None
                    else {
                        "claim": proposal.claim,
                        "status": ruled.get(
                            (proposal.subject, proposal.claim),
                            "nobody has ruled on this yet",
                        ),
                        "because": proposal.because,
                    }
                ),
            }
        )

    return ToolDefinition(
        name="describe_package",
        description=(
            "Look up one package in this codebase: which modules it holds, which tables it "
            "declares, what it depends on, what depends on it, and whether anyone has agreed "
            "it is a feature or a layer. Use this instead of guessing from the name — the "
            "answer comes from parsing the actual source."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Dotted package name, e.g. bacteria.app.graph",
                }
            },
            "required": ["name"],
        },
        handler=handler,
    )


def build_list_boundaries_tool(model: Model) -> ToolDefinition:
    """The stated rules, and how each one currently stands."""

    def handler(_: dict[str, Any]) -> str:
        verdict = model.verdict
        return json.dumps(
            {
                "crossed": [
                    {
                        "boundary": c.boundary.sentence,
                        "where": f"{c.edge.src} {c.edge.rel} {c.edge.dst}",
                        "line": c.edge.line,
                    }
                    for c in verdict.crossings
                ],
                "holding": [b.sentence for b in verdict.held],
                # Reported, not omitted. A list of passes and failures implies
                # everything was checked; four of these were never asked.
                "cannot_be_decided_from_imports": [
                    {"boundary": b.sentence, "checked_by": b.elsewhere} for b in verdict.undecidable
                ],
                "about_code_this_repository_lacks": [b.sentence for b in verdict.inapplicable],
            }
        )

    return ToolDefinition(
        name="list_boundaries",
        description=(
            "The architectural rules someone stated about this codebase and how each stands "
            "right now: crossed, holding, impossible to decide from imports, or about code "
            "this repository does not contain. Use it before claiming anything is or is not "
            "a violation."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )


def build_list_proposals_tool(model: Model, verdicts: Verdicts | None = None) -> ToolDefinition:
    """What the codebase's own repetition suggests, and who has ruled on it."""

    ruled: Verdicts = verdicts or {}

    def handler(_: dict[str, Any]) -> str:
        return json.dumps(
            {
                "proposals": [
                    {
                        "says": sentence(p),
                        "because": p.because,
                        "status": ruled.get((p.subject, p.claim), "open"),
                    }
                    for p in model.proposals
                ],
                "note": (
                    "These are proposals drawn from repetition, not facts. Only the ones "
                    "marked agreed have been ratified by a person."
                ),
            }
        )

    return ToolDefinition(
        name="list_proposals",
        description=(
            "What this codebase's own repetition suggests about itself — which module names "
            "recur often enough to be conventions, and which packages look like features or "
            "layers — together with whether a person has agreed, disagreed, or not yet ruled."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )


READ_ONLY = ("describe_package", "list_boundaries", "list_proposals")
"""The complete set of names the gate will allow.

A literal rather than a property of the tools, and deliberately: the gate must
be able to refuse a tool it has never heard of, which it cannot do by asking the
tool whether it is safe. Adding a tool means adding its name here, in the same
commit somebody has to think about.
"""
