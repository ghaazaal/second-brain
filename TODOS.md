# TODOS

## Rename `type` param to `note_type` in get_periodic_note

**What:** Rename the `type` parameter to `note_type` in `obsidian.py:250` (`get_periodic_note`) and the corresponding handler in `tools.py`.

**Why:** `type` is a Python builtin. Shadowing builtins is a code smell that causes subtle bugs in linters, type checkers, and refactoring tools. `note_type` is unambiguous.

**Pros:** Eliminates a linter warning; makes the codebase fully pyright-clean.

**Cons:** Tiny API surface change — only affects callers who use keyword args (none in current codebase).

**Context:** Found during architecture review on 2026-05-07. obsidian.py:250 and tools.py PeriodicNotesToolHandler both need updating together.

**Depends on / blocked by:** Nothing.

---

## Implement obsidian_analyze_vault (Vault Graph Analyzer)

**What:** Add a new MCP tool `obsidian_analyze_vault` that reads all `.md` files via REST API, parses `[[wikilinks]]`, computes degree centrality and connected components, and returns a Mermaid flowchart of the top-N hub notes.

**Why:** Gives users a structural view of their vault from within a Claude conversation — "which notes are the most important hubs?" — without any additional tooling.

**Pros:** Zero new dependencies (stdlib: `re`, `collections`); renders natively in Claude and in Obsidian; consistent with existing tool pattern; approved design doc with full spec.

**Cons:** For vaults >500 notes, ~50s of API calls (acceptable for analysis; not a hot path). Mermaid graphs get cluttered above ~40 nodes.

**Context:** Design doc approved 2026-04-28 on branch `claude/condescending-yalow-2c38a1`. Approach A (Mermaid, top-40 nodes by in-degree, connected components for clusters) is fully specified. Reuses `list_markdown_files_in_vault`, `get_file_contents`, `extract_dep_names` (from summarizer.py), and the `ToolHandler` base class.

**Depends on / blocked by:** URL encoding fix (Issue 2) should land first, since vault file reads drive the graph builder and paths with spaces would break it.
