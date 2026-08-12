"""Deterministic evaluation of runs that already happened.

Three pieces, deliberately separable:

- :mod:`~bacteria.app.evaluation.runs` rebuilds a run from the transcript,
- :mod:`~bacteria.app.evaluation.checks` judges runs and knows nothing about SQL,
- :mod:`~bacteria.app.evaluation.fixtures` produces runs to judge.

The split is what lets one set of checks serve two callers that otherwise have
nothing in common: the gate, which seeds fixtures and asserts, and
``bacteria-admin eval``, which reads whatever a deployment actually did.

This is the observability half of Part 8 turned into judgment. It is not a
feedback loop — nothing here turns a finding into a change, and a report that
nobody is obliged to act on is the dashboard the article warns about. Wiring the
gate to fail on findings is the smallest version of the missing half.
"""
