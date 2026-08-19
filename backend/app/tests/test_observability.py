"""What decides whether a process prints spans to its own stdout.

Exercises :func:`~bacteria.app.core.observability._should_print_spans` directly
rather than through :func:`~bacteria.app.core.observability.configure`, and that
is the reason the rule was extracted at all: `conftest` patches `configure` out
for the whole session, so a test reaching it would either observe the patch or
acquire a real exporter to watch. The decision is separable, so it is separate.
"""

from bacteria.app.core.observability import _should_print_spans


def test_a_process_with_nowhere_to_export_prints_spans():
    """No token means the console is the only record, so it must be written.

    This is the ordinary contributor's machine. Silencing it would leave someone
    with no Logfire account no way to see a span at all, which is the failure
    ADR 0003 avoided by not requiring a vendor before anything runs.
    """
    assert _should_print_spans(True, token="", override=None) is True


def test_a_process_that_exports_does_not_also_print():
    """A token means the spans are queryable, so printing them is noise in a log.

    The regression this exists for: with both on, a deployed worker printed a
    bare `SELECT` pair on every procrastinate poll, a few seconds apart,
    indefinitely — and the two lines saying an extraction job had finished were
    lost among them. Nothing was broken, which is what made it survive.
    """
    assert _should_print_spans(True, token="lf_xxx", override=None) is False


def test_a_developer_can_ask_for_both():
    """The default is a default, not a rule, and holding a token locally is normal.

    Without the override, configuring a token on a laptop would silently remove
    spans from the terminal — the exact confusion that prompted this change,
    arriving from the other direction.
    """
    assert _should_print_spans(True, token="lf_xxx", override=True) is True


def test_printing_can_be_silenced_with_no_exporter_at_all():
    """`false` means quiet, even though nothing is collecting the spans instead.

    Someone piping a process's output somewhere structured wants their format,
    not Logfire's, and "you may only have quiet if you also pay a vendor" would
    be an odd thing for this to enforce.
    """
    assert _should_print_spans(True, token="", override=False) is False


def test_a_surface_that_opted_out_cannot_be_overridden_by_configuration():
    """`console=False` is about what the stream *is*, so no variable may undo it.

    `bacteria-admin`'s stdout is where a person reads what a model said. If
    `BACTERIA_LOGFIRE_CONSOLE=true` could reach it, setting that variable for the
    API would break every conversation held from the same shell — twenty-three
    query spans between a question and its answer, which is what the `console`
    flag was added to stop.
    """
    assert _should_print_spans(False, token="", override=True) is False
    assert _should_print_spans(False, token="lf_xxx", override=True) is False
