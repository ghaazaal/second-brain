# Single responsibility: pure logic for building note context Claude will summarize.
# No file I/O here — receives content as strings, returns strings.

import re
from pathlib import Path
from typing import Callable

from . import note_io

NOTE_TYPES = ["reading_learning", "daily", "concerns", "work", "unknown"]

TEMPLATES: dict[str, list[str]] = {
    "reading_learning": ["Summary", "Key Ideas", "Insight", "Application"],
    "daily":            ["Summary", "What mattered", "Energy positive", "Energy negative", "Improvement"],
    "concerns":         ["Summary", "Core concern", "Possible causes", "Action", "Overthinking / avoidance"],
    "work":             ["Summary", "Decisions", "Open questions", "Risks", "Next actions"],
    "unknown":          ["Summary", "Main points", "Possible category", "Notes"],
}


def extract_dep_names(content: str) -> set[str]:
    """Pure function: extract linked note names from markdown content."""
    wikilinks = re.findall(r'\[\[([^\]|#]+?)(?:[#|][^\]]*)?\]\]', content)
    md_links  = re.findall(r'\[[^\]]*\]\(([^)]+\.md)\)', content)
    return {name.strip() for name in wikilinks} | {Path(p).stem for p in md_links}


def resolve_deps(dep_names: set[str], vault_root: Path) -> dict[str, str]:
    """Resolve dep names to their content via the filesystem. Skips any that cannot be found."""
    deps = {}
    for name in dep_names:
        found = note_io.find_note_by_name(name, vault_root)
        if found:
            deps[found.name] = note_io.load_note(found)
    return deps


def build_note_block(note_name: str, content: str, deps: dict[str, str]) -> str:
    """Pure function: format one note + its deps into a block Claude can classify and summarize."""
    lines = [f"## Note: {note_name}", "", "### Content", content.strip()]

    if deps:
        lines += ["", "### Linked notes (supporting context)"]
        for dep_name, dep_content in deps.items():
            lines += [f"#### {dep_name}", dep_content.strip(), ""]

    template_lines = [f"- **{t}**: " + ", ".join(sections) for t, sections in TEMPLATES.items()]
    dep_list = "\n".join(f"* {n}" for n in deps) if deps else "* none"

    lines += [
        "",
        "### Instructions for Claude",
        f"Classify this note into one of: {', '.join(NOTE_TYPES)}",
        "Then generate a structured summary using the matching template:",
        *template_lines,
        "",
        "Output:",
        "## Type",
        "<type>",
        "## Summary + Structured Takeaways",
        "<fill in the correct sections for the chosen type>",
        "## Dependencies used",
        dep_list,
    ]
    return "\n".join(lines)


def build_folder_context_from_notes(
    folder_label: str,
    notes: dict[str, str],
    deps_by_note: dict[str, dict[str, str]],
) -> str:
    """
    Core orchestration: build Claude-ready context from pre-loaded note content.

    folder_label: display name for the folder (used in the header)
    notes: {note_filename: content}
    deps_by_note: {note_filename: {dep_filename: dep_content}}
    """
    if not notes:
        return f"No markdown files found in {folder_label}"

    header = [f"# Obsidian folder: {folder_label}", f"# Notes found: {len(notes)}", ""]
    blocks = [
        build_note_block(name, content, deps_by_note.get(name, {}))
        for name, content in notes.items()
    ]
    return "\n".join(header) + "\n---\n".join(blocks)


def build_folder_context(folder: Path, vault_root: Path | None = None) -> str:
    """Filesystem-based entry point. Loads notes from disk and delegates to build_folder_context_from_notes."""
    if vault_root is None:
        vault_root = folder.parent
    notes = note_io.load_notes_in_folder(folder)

    deps_by_note = {
        name: resolve_deps(extract_dep_names(content), vault_root)
        for name, content in notes.items()
    }
    return build_folder_context_from_notes(
        folder_label=str(folder),
        notes=notes,
        deps_by_note=deps_by_note,
    )
