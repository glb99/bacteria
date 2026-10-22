from pathlib import Path

import pytest
from ingestion.evals import (
    EmptyGoldenSet,
    GoldenPage,
    GoldenSetMiss,
    evaluate,
    load_golden_set,
)


class _Returns:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_page(self, page: bytes) -> str:
        return self._text


def test_matching_page_passes() -> None:
    page = GoldenPage(name="one", page=b"%PDF-1", expected_text="alpha")

    evaluate(_Returns("alpha"), (page,))


def test_different_text_is_a_miss() -> None:
    page = GoldenPage(name="one", page=b"%PDF-1", expected_text="alpha")

    with pytest.raises(GoldenSetMiss) as caught:
        evaluate(_Returns("beta"), (page,))

    assert caught.value.misses[0].name == "one"
    assert caught.value.misses[0].expected_text == "alpha"
    assert caught.value.misses[0].returned_text == "beta"


def test_empty_set_fails() -> None:
    with pytest.raises(EmptyGoldenSet):
        evaluate(_Returns("alpha"), ())


def test_load_reads_page_and_expected_text_exactly(tmp_path: Path) -> None:
    case = tmp_path / "cover"
    case.mkdir()
    (case / "page.pdf").write_bytes(b"page-bytes")
    (case / "expected.txt").write_text("Line one\n", encoding="utf-8")

    loaded = load_golden_set(tmp_path)

    assert loaded == (
        GoldenPage(name="cover", page=b"page-bytes", expected_text="Line one\n"),
    )


def test_load_of_a_directory_with_no_cases_fails(tmp_path: Path) -> None:
    with pytest.raises(EmptyGoldenSet):
        load_golden_set(tmp_path)


def test_loaded_case_fails_when_the_extractor_changes(tmp_path: Path) -> None:
    case = tmp_path / "cover"
    case.mkdir()
    (case / "page.pdf").write_bytes(b"page-bytes")
    (case / "expected.txt").write_text("kept", encoding="utf-8")

    with pytest.raises(GoldenSetMiss):
        evaluate(_Returns("changed"), load_golden_set(tmp_path))
