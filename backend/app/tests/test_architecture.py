"""The derivation reads syntax, and the boundaries judge what it read.

No database anywhere in this file, which is unusual here and is the point: every
fact under test comes out of a parse, so a test that needed Postgres would be
testing something other than what the feature does.
"""

from pathlib import Path

from bacteria.app.architecture.checks import (
    BOUNDARIES,
    Boundary,
    _agent_reaches_into_the_app,
    _app_reaches_the_agents_own_root,
    _core_declares_a_table,
    _core_names_a_domain_concept,
    evaluate,
)
from bacteria.app.architecture.derive import Derived, Import, Module, derive

REPO = Path(__file__).resolve().parents[3]


def _write(root: Path, dotted: str, body: str) -> None:
    path = root.joinpath(*dotted.split(".")).with_suffix(".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _graph(*imports: Import, modules: tuple[str, ...] = ()) -> Derived:
    """A hand-built graph, so a check is tested against a shape and not a repo.

    Checks driven only over this codebase would pass for as long as nobody
    breaks it, which is precisely when a guard is never seen to work.
    """
    named = set(modules) | {edge.src for edge in imports} | {edge.dst for edge in imports}
    return Derived(
        modules={
            name: Module(
                name=name,
                path=f"{name.replace('.', '/')}.py",
                package=name.rsplit(".", 1)[0] if "." in name else name,
                tables=(),
            )
            for name in sorted(named)
        },
        imports=imports,
    )


class TestDerive:
    def test_a_package_is_named_by_its_directory(self, tmp_path: Path) -> None:
        """``__init__.py`` is the package itself, not a module inside it.

        Left as ``pkg.__init__`` the package would be a second node beside
        ``pkg``, and every import of the package would resolve to neither.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.thing", "")

        derived = derive({tmp_path: "t"})

        assert set(derived.modules) == {"pkg", "pkg.thing"}

    def test_a_symbol_import_resolves_to_the_module_holding_it(self, tmp_path: Path) -> None:
        """``from pkg.thing import Name`` is an edge to ``pkg.thing``.

        The syntax cannot say whether ``Name`` is a module or a symbol. Reading
        it only as a module would lose the edge entirely, so the dependency
        would be invisible to every boundary.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.thing", "")
        _write(tmp_path, "pkg.user", "from pkg.thing import Name\n")

        derived = derive({tmp_path: "t"})

        assert [(e.src, e.dst) for e in derived.imports] == [("pkg.user", "pkg.thing")]

    def test_a_relative_import_resolves_against_its_own_package(self, tmp_path: Path) -> None:
        """``from . import x`` names a sibling, not a top-level module.

        Resolved against the root instead, every relative import in a codebase
        would resolve to nothing and whole packages would look independent.

        It names **two** modules, and both edges are real: the sibling, and the
        package itself, whose ``__init__`` runs to reach the sibling. Dropping
        the second would hide a dependency on package-level code that genuinely
        executes. ``from .thing import Name`` names only one, because the
        alias resolves back to the module already yielded.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.thing", "")
        _write(tmp_path, "pkg.user", "from . import thing\n")

        derived = derive({tmp_path: "t"})

        assert [(e.src, e.dst) for e in derived.imports] == [
            ("pkg.user", "pkg"),
            ("pkg.user", "pkg.thing"),
        ]

    def test_an_external_import_is_not_an_edge(self, tmp_path: Path) -> None:
        """Only modules the walk actually found become edges.

        Without this the graph fills with every third-party package, and a
        boundary about internal layering is drowned by imports of ``os``.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.user", "import os\nfrom fastapi import APIRouter\n")

        derived = derive({tmp_path: "t"})

        assert derived.imports == ()

    def test_an_import_inside_a_function_is_deferred(self, tmp_path: Path) -> None:
        """A function-body import runs on call, not on load, and is marked.

        This is the distinction that stops a deliberate deferral -- the
        documented way out of a circular dependency -- being reported as a
        layering violation.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.thing", "")
        _write(
            tmp_path,
            "pkg.user",
            "import pkg.thing\n\n\ndef later():\n    import pkg.thing\n",
        )

        derived = derive({tmp_path: "t"})

        assert sorted(e.deferred for e in derived.imports) == [False, True]

    def test_a_deferred_import_stays_deferred_when_nested(self, tmp_path: Path) -> None:
        """Depth inside a function does not restore module-level status.

        An import in a ``try`` inside an ``if`` inside a function is still a
        call-time import, and a walk that only looked one level down would call
        it a load-time one.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.thing", "")
        _write(
            tmp_path,
            "pkg.user",
            "def later():\n"
            "    if True:\n"
            "        try:\n"
            "            import pkg.thing\n"
            "        except ImportError:\n"
            "            pass\n",
        )

        derived = derive({tmp_path: "t"})

        assert [e.deferred for e in derived.imports] == [True]

    def test_a_module_level_import_inside_a_conditional_is_not_deferred(
        self, tmp_path: Path
    ) -> None:
        """An ``if`` at module level still runs on load.

        Treating every nested statement as deferred would exempt a whole class
        of real module-level imports from every boundary.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.thing", "")
        _write(tmp_path, "pkg.user", "if True:\n    import pkg.thing\n")

        derived = derive({tmp_path: "t"})

        assert [e.deferred for e in derived.imports] == [False]

    def test_a_table_is_read_from_its_literal(self, tmp_path: Path) -> None:
        """``__tablename__`` is collected without importing the module.

        A derivation that imported the code it describes could be broken by the
        code it describes, which is the failure that makes such a tool
        untrusted.
        """
        _write(tmp_path, "pkg", 'class Thing:\n    __tablename__ = "thing"\n')

        derived = derive({tmp_path: "t"})

        assert derived.tables == ("thing",)

    def test_a_file_that_does_not_parse_is_skipped(self, tmp_path: Path) -> None:
        """One broken file does not deny an answer about every other file.

        This runs over a whole tree, often a dirty one; raising would make the
        tool useless exactly when somebody is mid-edit.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.broken", "def (\n")
        _write(tmp_path, "pkg.fine", "")

        derived = derive({tmp_path: "t"})

        assert "pkg.fine" in derived.modules
        assert derived.imports == ()

    def test_a_prefix_does_not_match_a_longer_name(self, tmp_path: Path) -> None:
        """``within("pkg.core")`` must not claim ``pkg.corex``.

        Boundaries are stated about regions and a region is a prefix, so a bare
        ``startswith`` silently widens every rule to neighbouring packages.
        """
        _write(tmp_path, "pkg.__init__", "")
        _write(tmp_path, "pkg.core", "")
        _write(tmp_path, "pkg.corex", "")

        derived = derive({tmp_path: "t"})

        assert derived.within("pkg.core") == ("pkg.core",)


class TestBoundariesCanFail:
    """Every rule is shown rejecting something.

    A guard nobody has seen fail is a guard nobody has tested, and all four of
    these currently hold over this codebase -- so passing on the real tree is no
    evidence at all that they work.
    """

    def test_the_agent_may_not_reach_into_the_application(self) -> None:
        """An agent module importing an application module is caught.

        This is the boundary the two-package split exists to hold: the agent is
        vendorable only while it names nothing above it.
        """
        offending = Import(
            src="bacteria.agent.session.store",
            dst="bacteria.app.core.db",
            deferred=False,
            line=4,
        )
        clean = Import(
            src="bacteria.app.chat.service",
            dst="bacteria.agent.session.store",
            deferred=False,
            line=9,
        )

        assert list(_agent_reaches_into_the_app(_graph(offending, clean))) == [offending]

    def test_the_application_may_not_import_the_agents_own_root(self) -> None:
        """Two composition roots stay two.

        ``bacteria.agent.interfaces`` composes the agent's own process; the
        application composing itself out of it would make one root wearing two
        names.
        """
        offending = Import(
            src="bacteria.app.entrypoints.cli",
            dst="bacteria.agent.interfaces.cli",
            deferred=False,
            line=12,
        )

        assert list(_app_reaches_the_agents_own_root(_graph(offending))) == [offending]

    def test_core_may_not_name_a_feature_at_module_level(self) -> None:
        """Core importing a feature on load is a crossing; deferring is not.

        Both edges exist in this codebase, and a check that cannot separate them
        reports six violations on an intact boundary.
        """
        offending = Import(
            src="bacteria.app.core.db",
            dst="bacteria.app.chat.models",
            deferred=False,
            line=7,
        )
        deferred = Import(
            src="bacteria.app.core.jobs",
            dst="bacteria.app.chat.tasks",
            deferred=True,
            line=117,
        )
        inward = Import(
            src="bacteria.app.chat.service",
            dst="bacteria.app.core.db",
            deferred=False,
            line=3,
        )

        found = list(_core_names_a_domain_concept(_graph(offending, deferred, inward)))

        assert found == [offending]

    def test_core_may_not_declare_a_table(self) -> None:
        """A table under ``core/`` means a domain concept moved into it.

        Tables are the least reversible thing a package can own, so this is the
        form of the rule that costs most to discover late.
        """
        derived = Derived(
            modules={
                "bacteria.app.core.db": Module(
                    name="bacteria.app.core.db",
                    path="core/db.py",
                    package="bacteria.app.core",
                    tables=("chat_session",),
                ),
                "bacteria.app.chat.models": Module(
                    name="bacteria.app.chat.models",
                    path="chat/models.py",
                    package="bacteria.app.chat",
                    tables=("chat_transcript_item",),
                ),
            },
            imports=(),
        )

        assert [edge.dst for edge in _core_declares_a_table(derived)] == ["chat_session"]


class TestVerdict:
    def test_an_undecidable_boundary_is_reported_rather_than_dropped(self) -> None:
        """A rule no import can settle appears in the verdict, unjudged.

        Dropping it would make a report listing four passes look like a clean
        bill of health on eight rules, which is the failure this feature exists
        to be the opposite of.
        """
        stated_only = Boundary(
            name="contains-no-logic",
            sentence="Entrypoints hold configuration, never logic.",
            elsewhere="review",
        )

        verdict = evaluate(_graph(modules=("pkg",)), [stated_only])

        assert verdict.undecidable == (stated_only,)
        assert verdict.held == ()
        assert verdict.clean is True

    def test_a_crossing_makes_the_verdict_unclean(self) -> None:
        """One crossing is enough to fail, which is what makes this a gate."""
        offending = Import(
            src="bacteria.agent.tools.memory",
            dst="bacteria.app.chat.models",
            deferred=False,
            line=2,
        )

        verdict = evaluate(_graph(offending), BOUNDARIES)

        assert verdict.clean is False
        assert [c.edge for c in verdict.crossings] == [offending]

    def test_this_codebase_holds_every_boundary_it_can_decide(self) -> None:
        """The real tree passes, and this is the regression the feature is for.

        Distinct from the tests above: those prove the rules can reject, this
        proves the codebase currently satisfies them. Losing either makes the
        other meaningless.
        """
        roots = {path: path.parts[-2] for path in sorted((REPO / "backend").glob("*/src"))}
        assert roots, "no source roots found; the layout moved"

        verdict = evaluate(derive(roots))

        assert verdict.crossings == ()
        assert len(verdict.held) + len(verdict.undecidable) == len(BOUNDARIES)
