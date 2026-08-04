"""Load-bearing invariant tests for the add_note tool (Part 6 decisions)."""

from bacteria.tools.notes import build_add_note_tool


def test_add_note_appends_without_clobbering_existing_notes(tmp_path):
    notes_path = tmp_path / "notes.txt"
    tool = build_add_note_tool(notes_path)

    tool.handler({"text": "first"})
    tool.handler({"text": "second"})

    assert notes_path.read_text(encoding="utf-8") == "first\nsecond\n"


def test_add_note_creates_parent_directories(tmp_path):
    notes_path = tmp_path / "nested" / "dir" / "notes.txt"
    tool = build_add_note_tool(notes_path)

    tool.handler({"text": "hello"})

    assert notes_path.exists()


def test_add_note_returns_confirmation_with_the_saved_text(tmp_path):
    tool = build_add_note_tool(tmp_path / "notes.txt")

    result = tool.handler({"text": "buy milk"})

    assert "buy milk" in result


def test_add_note_schema_never_exposes_the_handler():
    tool = build_add_note_tool()

    schema = tool.to_schema()

    assert set(schema.keys()) == {"name", "description", "input_schema"}
    assert schema["name"] == "add_note"
