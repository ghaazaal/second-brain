from collections.abc import Sequence
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
import json
from pathlib import PurePosixPath
from . import obsidian
from . import summarizer

TOOL_LIST_FILES_IN_VAULT = "obsidian_list_files_in_vault"
TOOL_LIST_FILES_IN_DIR = "obsidian_list_files_in_dir"


def build_folder_context_from_api(api: obsidian.Obsidian, folder_path: str) -> str:
    folder_path = folder_path.replace("\\", "/").strip("/")
    filepaths = api.list_markdown_files_in_dir(folder_path)
    notes = {
        PurePosixPath(fp).name: api.get_file_contents(fp)
        for fp in filepaths
    }

    # Build vault stem→path index lazily (only if any note has links)
    dep_paths_by_stem: dict[str, str] | None = None

    def get_dep_paths() -> dict[str, str]:
        nonlocal dep_paths_by_stem
        if dep_paths_by_stem is None:
            dep_paths_by_stem = {}
            for fp in api.list_markdown_files_in_vault():
                dep_paths_by_stem.setdefault(PurePosixPath(fp).stem.lower(), fp)
        return dep_paths_by_stem

    deps_by_note: dict[str, dict[str, str]] = {}
    for note_name, content in notes.items():
        dep_names = summarizer.extract_dep_names(content)
        if not dep_names:
            deps_by_note[note_name] = {}
            continue
        index = get_dep_paths()
        deps: dict[str, str] = {}
        for dep_name in dep_names:
            dep_path = index.get(PurePosixPath(dep_name).stem.lower())
            if dep_path:
                deps[PurePosixPath(dep_path).name] = api.get_file_contents(dep_path)
        deps_by_note[note_name] = deps

    return summarizer.build_folder_context_from_notes(
        folder_label=folder_path,
        notes=notes,
        deps_by_note=deps_by_note,
    )


class ToolHandler():
    def __init__(self, tool_name: str, api: obsidian.Obsidian):
        self.name = tool_name
        self.api = api

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        raise NotImplementedError()


class ListFilesInVaultToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__(TOOL_LIST_FILES_IN_VAULT, api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all files and directories in the root directory of your Obsidian vault.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        files = self.api.list_files_in_vault()
        return [TextContent(type="text", text=json.dumps(files, indent=2))]


class ListFilesInDirToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__(TOOL_LIST_FILES_IN_DIR, api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all files and directories that exist in a specific Obsidian directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dirpath": {
                        "type": "string",
                        "description": "Path to list files from (relative to your vault root). Note that empty directories will not be returned."
                    },
                },
                "required": ["dirpath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        files = self.api.list_files_in_dir(args["dirpath"])
        return [TextContent(type="text", text=json.dumps(files, indent=2))]


class GetFileContentsToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_get_file_contents", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Return the content of a single file in your vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the relevant file (relative to your vault root).",
                        "format": "path"
                    },
                },
                "required": ["filepath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        content = self.api.get_file_contents(args["filepath"])
        return [TextContent(type="text", text=json.dumps(content, indent=2))]


class SearchToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_simple_search", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Simple search for documents matching a specified text query across all files in the vault.
            Use this tool when you want to do a simple text search""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to a simple search for in the vault."
                    },
                    "context_length": {
                        "type": "integer",
                        "description": "How much context to return around the matching string (default: 100)",
                        "default": 100
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        context_length = args.get("context_length", 100)
        results = self.api.search(args["query"], context_length)

        formatted_results = []
        for result in results:
            formatted_matches = []
            for match in result.get('matches', []):
                context = match.get('context', '')
                match_pos = match.get('match', {})
                start = match_pos.get('start', 0)
                end = match_pos.get('end', 0)
                formatted_matches.append({
                    'context': context,
                    'match_position': {'start': start, 'end': end}
                })
            formatted_results.append({
                'filename': result.get('filename', ''),
                'score': result.get('score', 0),
                'matches': formatted_matches
            })

        return [TextContent(type="text", text=json.dumps(formatted_results, indent=2))]


class AppendContentToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_append_content", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Append content to a new or existing file in the vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file (relative to vault root)",
                        "format": "path"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to append to the file"
                    }
                },
                "required": ["filepath", "content"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        self.api.append_content(args["filepath"], args["content"])
        return [TextContent(type="text", text=f"Successfully appended content to {args['filepath']}")]


class PatchContentToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_patch_content", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Insert content into an existing note relative to a heading, block reference, or frontmatter field.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file (relative to vault root)",
                        "format": "path"
                    },
                    "operation": {
                        "type": "string",
                        "description": "Operation to perform (append, prepend, or replace)",
                        "enum": ["append", "prepend", "replace"]
                    },
                    "target_type": {
                        "type": "string",
                        "description": "Type of target to patch",
                        "enum": ["heading", "block", "frontmatter"]
                    },
                    "target": {
                        "type": "string",
                        "description": "Target identifier (heading path, block reference, or frontmatter field)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to insert"
                    }
                },
                "required": ["filepath", "operation", "target_type", "target", "content"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        self.api.patch_content(
            args["filepath"],
            args["operation"],
            args["target_type"],
            args["target"],
            args["content"],
        )
        return [TextContent(type="text", text=f"Successfully patched content in {args['filepath']}")]


class PutContentToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_put_content", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Create a new file in your vault or update the content of an existing one in your vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the relevant file (relative to your vault root)",
                        "format": "path"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content of the file you would like to upload"
                    }
                },
                "required": ["filepath", "content"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        self.api.put_content(args["filepath"], args["content"])
        return [TextContent(type="text", text=f"Successfully uploaded content to {args['filepath']}")]


class DeleteFileToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_delete_file", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Delete a file or directory from the vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file or directory to delete (relative to vault root)",
                        "format": "path"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Confirmation to delete the file (must be true)",
                        "default": False
                    }
                },
                "required": ["filepath", "confirm"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if not args.get("confirm", False):
            raise RuntimeError("confirm must be set to true to delete a file")
        self.api.delete_file(args["filepath"])
        return [TextContent(type="text", text=f"Successfully deleted {args['filepath']}")]


class ComplexSearchToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_complex_search", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Complex search for documents using a JsonLogic query.
           Supports standard JsonLogic operators plus 'glob' and 'regexp' for pattern matching. Results must be non-falsy.

           Use this tool when you want to do a complex search, e.g. for all documents with certain tags etc.
           ALWAYS follow query syntax in examples.

           Examples
            1. Match all markdown files
            {"glob": ["*.md", {"var": "path"}]}

            2. Match all markdown files with 1221 substring inside them
            {
              "and": [
                { "glob": ["*.md", {"var": "path"}] },
                { "regexp": [".*1221.*", {"var": "content"}] }
              ]
            }

            3. Match all markdown files in Work folder containing name Keaton
            {
              "and": [
                { "glob": ["*.md", {"var": "path"}] },
                { "regexp": [".*Work.*", {"var": "path"}] },
                { "regexp": ["Keaton", {"var": "content"}] }
              ]
            }
           """,
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "object",
                        "description": "JsonLogic query object. ALWAYS follow query syntax in examples. \
                            Example 1: {\"glob\": [\"*.md\", {\"var\": \"path\"}]} matches all markdown files \
                            Example 2: {\"and\": [{\"glob\": [\"*.md\", {\"var\": \"path\"}]}, {\"regexp\": [\".*1221.*\", {\"var\": \"content\"}]}]} matches all markdown files with 1221 substring inside them \
                            Example 3: {\"and\": [{\"glob\": [\"*.md\", {\"var\": \"path\"}]}, {\"regexp\": [\".*Work.*\", {\"var\": \"path\"}]}, {\"regexp\": [\"Keaton\", {\"var\": \"content\"}]}]} matches all markdown files in Work folder containing name Keaton \
                        "
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        results = self.api.search_json(args["query"])
        return [TextContent(type="text", text=json.dumps(results, indent=2))]


class BatchGetFileContentsToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_batch_get_file_contents", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Return the contents of multiple files in your vault, concatenated with headers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepaths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "Path to a file (relative to your vault root)",
                            "format": "path"
                        },
                        "description": "List of file paths to read"
                    },
                },
                "required": ["filepaths"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        content = self.api.get_batch_file_contents(args["filepaths"])
        return [TextContent(type="text", text=content)]


class PeriodicNotesToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_get_periodic_note", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get current periodic note for the specified period.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "type": {
                        "type": "string",
                        "description": "The type of data to get ('content' or 'metadata'). 'content' returns just the content in Markdown format. 'metadata' includes note metadata (including paths, tags, etc.) and the content.",
                        "default": "content",
                        "enum": ["content", "metadata"]
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")

        note_type = args.get("type", "content")
        valid_types = ["content", "metadata"]
        if note_type not in valid_types:
            raise RuntimeError(f"Invalid type: {note_type}. Must be one of: {', '.join(valid_types)}")

        content = self.api.get_periodic_note(period, note_type)
        return [TextContent(type="text", text=content)]


class RecentPeriodicNotesToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_get_recent_periodic_notes", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get most recent periodic notes for the specified period type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of notes to return (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include note content (default: false)",
                        "default": False
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")

        limit = args.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")

        include_content = args.get("include_content", False)
        if not isinstance(include_content, bool):
            raise RuntimeError(f"Invalid include_content: {include_content}. Must be a boolean")

        results = self.api.get_recent_periodic_notes(period, limit, include_content)
        return [TextContent(type="text", text=json.dumps(results, indent=2))]


class RecentChangesToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_get_recent_changes", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get recently modified files in the vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of files to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "days": {
                        "type": "integer",
                        "description": "Only include files modified within this many days (default: 90)",
                        "minimum": 1,
                        "default": 90
                    }
                }
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        limit = args.get("limit", 10)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")

        days = args.get("days", 90)
        if not isinstance(days, int) or days < 1:
            raise RuntimeError(f"Invalid days: {days}. Must be a positive integer")

        results = self.api.get_recent_changes(limit, days)
        return [TextContent(type="text", text=json.dumps(results, indent=2))]


class SummarizeFolderToolHandler(ToolHandler):
    def __init__(self, api: obsidian.Obsidian):
        super().__init__("obsidian_summarize_folder", api)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Read all markdown notes in an Obsidian folder, resolve their first-level "
                "wikilink and markdown link dependencies, and return the full content ready for "
                "classification and summarization. After calling this tool, classify each note as "
                "one of: reading_learning, daily, concerns, work, unknown — then generate a "
                "structured summary using the matching template sections."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": (
                            "Path to the Obsidian folder to summarize, relative to the vault root "
                            "(e.g. 'Projects/Data Engineering')."
                        )
                    }
                },
                "required": ["folder_path"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        context = build_folder_context_from_api(self.api, args["folder_path"])
        return [TextContent(type="text", text=context)]
