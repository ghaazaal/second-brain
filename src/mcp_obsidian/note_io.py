# Single responsibility: all filesystem access for markdown notes.
# Nothing in here does logic — only reads and finds files.

from pathlib import Path


def load_notes_in_folder(folder: Path) -> dict[str, str]:
    return {
        f.name: f.read_text(encoding="utf-8", errors="ignore")
        for f in sorted(folder.glob("*.md"))
    }


def find_note_by_name(name: str, vault_root: Path) -> Path | None:
    """Case-insensitive search for a .md file by stem across the vault."""
    for md in vault_root.rglob("*.md"):
        if md.stem.lower() == name.lower():
            return md
    return None


def load_note(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")
