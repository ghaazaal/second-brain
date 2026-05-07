"""Tests for obsidian.py pure helpers and Obsidian client behaviour."""
import pytest
import responses as resp_lib
from mcp_obsidian.obsidian import (
    _normalize_vault_path,
    _join_vault_path,
    Obsidian,
)


class TestNormalizeVaultPath:
    def test_backslashes_converted(self):
        assert _normalize_vault_path("a\\b\\c") == "a/b/c"

    def test_leading_slash_stripped(self):
        assert _normalize_vault_path("/a/b") == "a/b"

    def test_trailing_slash_stripped(self):
        assert _normalize_vault_path("a/b/") == "a/b"

    def test_empty_string(self):
        assert _normalize_vault_path("") == ""

    def test_windows_path(self):
        assert _normalize_vault_path("\\Projects\\Notes\\") == "Projects/Notes"


class TestJoinVaultPath:
    def test_simple_join(self):
        assert _join_vault_path("Projects", "note.md") == "Projects/note.md"

    def test_empty_dirpath_returns_entry(self):
        assert _join_vault_path("", "note.md") == "note.md"

    def test_already_joined_not_doubled(self):
        result = _join_vault_path("Projects", "Projects/note.md")
        assert result == "Projects/note.md"

    def test_nested(self):
        assert _join_vault_path("a/b", "c.md") == "a/b/c.md"


class TestObsidianInit:
    def test_defaults_resolved_at_init_not_definition(self, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_HOST", "myhost")
        monkeypatch.setenv("OBSIDIAN_PORT", "9999")
        monkeypatch.setenv("OBSIDIAN_PROTOCOL", "http")
        api = Obsidian(api_key="testkey")
        assert api.host == "myhost"
        assert api.port == 9999
        assert api.protocol == "http"

    def test_explicit_args_override_env(self, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_HOST", "envhost")
        api = Obsidian(api_key="key", host="explicit", port=1234, protocol="https")
        assert api.host == "explicit"
        assert api.port == 1234

    def test_invalid_protocol_defaults_to_https(self):
        api = Obsidian(api_key="key", protocol="ftp")
        assert api.protocol == "https"

    def test_make_vault_url_encodes_spaces(self):
        api = Obsidian(api_key="key", host="127.0.0.1", port=27124, protocol="https")
        url = api._make_vault_url("My Folder/my note.md")
        assert "My%20Folder/my%20note.md" in url

    def test_make_vault_url_preserves_slashes(self):
        api = Obsidian(api_key="key", host="127.0.0.1", port=27124, protocol="https")
        url = api._make_vault_url("a/b/c.md")
        assert "a/b/c.md" in url


class TestObsidianVaultListCache:
    @resp_lib.activate
    def test_second_call_uses_cache(self):
        api = Obsidian(api_key="key", host="127.0.0.1", port=27124, protocol="https")

        # Register vault root + one subdir
        resp_lib.add(
            resp_lib.GET,
            "https://127.0.0.1:27124/vault/",
            json={"files": ["note.md", "sub/"]},
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://127.0.0.1:27124/vault/sub/",
            json={"files": ["sub/other.md"]},
            status=200,
        )

        first = api.list_markdown_files_in_vault()
        # Second call — no new HTTP responses registered, would fail if it hits the network
        second = api.list_markdown_files_in_vault()
        assert first == second

    @resp_lib.activate
    def test_cache_expires_after_ttl(self, monkeypatch):
        import time
        api = Obsidian(api_key="key", host="127.0.0.1", port=27124, protocol="https")

        resp_lib.add(
            resp_lib.GET,
            "https://127.0.0.1:27124/vault/",
            json={"files": ["a.md"]},
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "https://127.0.0.1:27124/vault/",
            json={"files": ["b.md"]},
            status=200,
        )

        first = api.list_markdown_files_in_vault()
        # Simulate TTL expiry
        api._vault_list_cache_ts -= 60
        second = api.list_markdown_files_in_vault()
        assert first == ["a.md"]
        assert second == ["b.md"]


class TestDeleteFileConfirmGuard:
    def test_delete_without_confirm_raises(self):
        """DeleteFileToolHandler must refuse when confirm=False."""
        from mcp_obsidian.tools import DeleteFileToolHandler
        from unittest.mock import MagicMock
        api = MagicMock()
        handler = DeleteFileToolHandler(api)
        with pytest.raises(RuntimeError, match="confirm must be set to true"):
            handler.run_tool({"filepath": "notes/test.md", "confirm": False})
        api.delete_file.assert_not_called()

    def test_delete_with_confirm_calls_api(self):
        from mcp_obsidian.tools import DeleteFileToolHandler
        from unittest.mock import MagicMock
        api = MagicMock()
        handler = DeleteFileToolHandler(api)
        handler.run_tool({"filepath": "notes/test.md", "confirm": True})
        api.delete_file.assert_called_once_with("notes/test.md")
