"""Tests for summarizer.py pure functions — no network, no filesystem."""
import pytest
from mcp_obsidian.summarizer import (
    extract_dep_names,
    build_note_block,
    build_folder_context_from_notes,
    NOTE_TYPES,
    TEMPLATES,
)


class TestExtractDepNames:
    def test_wikilink(self):
        assert extract_dep_names("See [[My Note]]") == {"My Note"}

    def test_wikilink_with_alias(self):
        assert extract_dep_names("See [[My Note|display text]]") == {"My Note"}

    def test_wikilink_with_section(self):
        # section anchor stripped by regex — [[Note#Heading]] → "Note"
        result = extract_dep_names("See [[Note#Heading]]")
        assert "Note" in result

    def test_markdown_link(self):
        result = extract_dep_names("See [label](path/to/note.md)")
        assert "note" in result  # stem only

    def test_multiple_links(self):
        content = "[[Alpha]] and [[Beta]] and [g](gamma.md)"
        result = extract_dep_names(content)
        assert {"Alpha", "Beta", "gamma"} == result

    def test_no_links(self):
        assert extract_dep_names("Just plain text with no links.") == set()

    def test_empty_string(self):
        assert extract_dep_names("") == set()

    def test_ignores_non_md_markdown_links(self):
        # Only .md links should be captured
        result = extract_dep_names("[label](image.png)")
        assert result == set()


class TestBuildNoteBlock:
    def test_no_deps(self):
        block = build_note_block("my_note.md", "Some content", {})
        assert "## Note: my_note.md" in block
        assert "### Content" in block
        assert "Some content" in block
        assert "### Linked notes" not in block
        assert "* none" in block

    def test_with_deps(self):
        block = build_note_block("note.md", "Content here", {"dep.md": "Dep content"})
        assert "### Linked notes (supporting context)" in block
        assert "#### dep.md" in block
        assert "Dep content" in block

    def test_all_note_types_in_instructions(self):
        block = build_note_block("n.md", "c", {})
        for t in NOTE_TYPES:
            assert t in block

    def test_all_template_sections_present(self):
        block = build_note_block("n.md", "c", {})
        for sections in TEMPLATES.values():
            for section in sections:
                assert section in block

    def test_content_stripped(self):
        block = build_note_block("n.md", "  content with whitespace  ", {})
        assert "content with whitespace" in block

    def test_output_structure(self):
        block = build_note_block("n.md", "c", {})
        assert "## Type" in block
        assert "## Summary + Structured Takeaways" in block
        assert "## Dependencies used" in block


class TestBuildFolderContextFromNotes:
    def test_empty_notes(self):
        result = build_folder_context_from_notes("MyFolder", {}, {})
        assert "No markdown files found in MyFolder" in result

    def test_header_contains_folder_and_count(self):
        notes = {"a.md": "content a", "b.md": "content b"}
        result = build_folder_context_from_notes("MyFolder", notes, {})
        assert "# Obsidian folder: MyFolder" in result
        assert "# Notes found: 2" in result

    def test_each_note_block_present(self):
        notes = {"a.md": "content a", "b.md": "content b"}
        result = build_folder_context_from_notes("F", notes, {})
        assert "## Note: a.md" in result
        assert "## Note: b.md" in result

    def test_deps_forwarded_to_block(self):
        notes = {"main.md": "[[dep]]"}
        deps = {"main.md": {"dep.md": "dependency content"}}
        result = build_folder_context_from_notes("F", notes, deps)
        assert "dependency content" in result

    def test_missing_deps_entry_defaults_to_empty(self):
        notes = {"a.md": "content"}
        # No entry in deps_by_note for a.md
        result = build_folder_context_from_notes("F", notes, {})
        assert "## Note: a.md" in result
        assert "* none" in result
