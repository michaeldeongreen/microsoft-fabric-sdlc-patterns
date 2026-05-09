"""Tests for scripts/deploy_bulk.py.

Covers the pure functions extracted from the bulk-import deployment script.
The orchestration in main() and the network-dependent poll loop are not
unit-tested here — those are validated end-to-end via the deploy workflows.
"""

from __future__ import annotations

import base64
import pathlib
from unittest import mock

import pytest

from deploy_bulk import (
    EXCLUDED_FILES,
    acquire_token,
    build_definition_parts,
    check_per_item_status,
    interpret_post_response,
)


# ---------- build_definition_parts ----------


def _make_item_file(repo_dir: pathlib.Path, item_path: str, content: bytes = b"x") -> None:
    """Create a file under repo_dir/<item_path>, ensuring parent dirs exist."""
    full = repo_dir / item_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)


def test_build_definition_parts_happy_path(tmp_path: pathlib.Path) -> None:
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py", b"print('hi')")
    parts = build_definition_parts(tmp_path)
    assert len(parts) == 1
    assert parts[0]["path"] == "/MyItem.Notebook/notebook-content.py"
    assert parts[0]["payloadType"] == "InlineBase64"
    assert base64.b64decode(parts[0]["payload"]) == b"print('hi')"


def test_build_definition_parts_excludes_gitkeep(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".gitkeep").write_bytes(b"")
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py")
    parts = build_definition_parts(tmp_path)
    paths = [p["path"] for p in parts]
    assert "/.gitkeep" not in paths
    assert "/MyItem.Notebook/notebook-content.py" in paths


def test_build_definition_parts_excludes_parameter_yml(tmp_path: pathlib.Path) -> None:
    (tmp_path / "parameter.yml").write_bytes(b"find_replace: []")
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py")
    parts = build_definition_parts(tmp_path)
    paths = [p["path"] for p in parts]
    assert "/parameter.yml" not in paths


def test_build_definition_parts_excludes_root_level_files(tmp_path: pathlib.Path) -> None:
    """Anything directly under repository_directory (not in *.<Type>/) is skipped."""
    (tmp_path / "README.md").write_bytes(b"# notes")
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py")
    parts = build_definition_parts(tmp_path)
    paths = [p["path"] for p in parts]
    assert "/README.md" not in paths
    assert "/MyItem.Notebook/notebook-content.py" in paths


def test_build_definition_parts_walks_recursively(tmp_path: pathlib.Path) -> None:
    _make_item_file(tmp_path, "Item.Notebook/.platform", b"{}")
    _make_item_file(tmp_path, "Item.Notebook/notebook-content.py", b"x")
    _make_item_file(
        tmp_path, "Item.SemanticModel/definition/tables/t.tmdl", b"table t"
    )
    parts = build_definition_parts(tmp_path)
    assert len(parts) == 3
    paths = sorted(p["path"] for p in parts)
    assert paths == [
        "/Item.Notebook/.platform",
        "/Item.Notebook/notebook-content.py",
        "/Item.SemanticModel/definition/tables/t.tmdl",
    ]


def test_build_definition_parts_empty_repo_exits(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit) as exc:
        build_definition_parts(tmp_path)
    assert "No item definition files found" in str(exc.value)


def test_build_definition_parts_missing_dir_exits(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit) as exc:
        build_definition_parts(tmp_path / "does_not_exist")
    assert "Repository directory not found" in str(exc.value)


def test_excluded_files_constant_includes_known_excludes() -> None:
    """Sanity check on the constant — protects against accidental edits."""
    assert "parameter.yml" in EXCLUDED_FILES
    assert ".gitkeep" in EXCLUDED_FILES


# ---------- check_per_item_status ----------


def test_check_per_item_status_all_succeeded(capsys: pytest.CaptureFixture) -> None:
    result = {
        "importItemDefinitionsDetails": [
            {"itemDisplayName": "X", "itemType": "Notebook", "operationStatus": "Succeeded"},
            {"itemDisplayName": "Y", "itemType": "Report", "operationStatus": "Succeeded"},
        ]
    }
    check_per_item_status(result)  # should not raise
    assert "All 2 items deployed successfully" in capsys.readouterr().out


def test_check_per_item_status_one_failed_exits() -> None:
    result = {
        "importItemDefinitionsDetails": [
            {"itemDisplayName": "X", "itemType": "Notebook", "operationStatus": "Succeeded"},
            {"itemDisplayName": "Y", "itemType": "Report", "operationStatus": "Failed"},
        ]
    }
    with pytest.raises(SystemExit) as exc:
        check_per_item_status(result)
    assert "1 item(s) failed" in str(exc.value)
    assert "Y (Report): Failed" in str(exc.value)


def test_check_per_item_status_succeeded_despite_failures_exits() -> None:
    """SucceededDespiteFailures is treated as a failure for build-fail purposes."""
    result = {
        "importItemDefinitionsDetails": [
            {
                "itemDisplayName": "Z",
                "itemType": "Notebook",
                "operationStatus": "SucceededDespiteFailures",
            },
        ]
    }
    with pytest.raises(SystemExit) as exc:
        check_per_item_status(result)
    assert "1 item(s) failed" in str(exc.value)
    assert "SucceededDespiteFailures" in str(exc.value)


def test_check_per_item_status_missing_details_exits() -> None:
    with pytest.raises(SystemExit) as exc:
        check_per_item_status({})
    assert "no importItemDefinitionsDetails" in str(exc.value)


# ---------- interpret_post_response ----------


def test_interpret_post_response_sync_200() -> None:
    body = {"importItemDefinitionsDetails": [{"itemId": "abc"}]}
    action = interpret_post_response(200, body, {})
    assert action == ("sync", body)


def test_interpret_post_response_async_202() -> None:
    headers = {"x-ms-operation-id": "op-123", "Retry-After": "45"}
    action = interpret_post_response(202, {}, headers)
    assert action == ("async", "op-123", 45)


def test_interpret_post_response_async_202_default_retry_after() -> None:
    """When Retry-After is missing, fall back to POLL_FALLBACK_SECONDS (30)."""
    headers = {"x-ms-operation-id": "op-456"}
    action = interpret_post_response(202, {}, headers)
    assert action == ("async", "op-456", 30)


def test_interpret_post_response_missing_op_id() -> None:
    """A 202 response without x-ms-operation-id is treated as malformed."""
    action = interpret_post_response(202, {}, {})
    assert action == ("missing_op_id",)


def test_interpret_post_response_unexpected_status() -> None:
    action = interpret_post_response(500, {}, {})
    assert action == ("error", 500)


# ---------- acquire_token ----------


def test_acquire_token_success(capsys: pytest.CaptureFixture) -> None:
    fake_resp = mock.Mock(status_code=200)
    fake_resp.json.return_value = {"access_token": "fake-token-xyz"}
    with mock.patch("deploy_bulk.requests.post", return_value=fake_resp) as post:
        token = acquire_token("tenant", "client", "secret")
    assert token == "fake-token-xyz"
    # Verify the call was shaped correctly
    post.assert_called_once()
    call_kwargs = post.call_args.kwargs
    assert call_kwargs["data"]["grant_type"] == "client_credentials"
    assert call_kwargs["data"]["scope"] == "https://api.fabric.microsoft.com/.default"
    # Workflow log mask was emitted
    assert "::add-mask::fake-token-xyz" in capsys.readouterr().out


def test_acquire_token_failure_exits() -> None:
    fake_resp = mock.Mock(status_code=401, text="Unauthorized")
    with mock.patch("deploy_bulk.requests.post", return_value=fake_resp):
        with pytest.raises(SystemExit) as exc:
            acquire_token("tenant", "client", "secret")
    assert "Token acquisition failed" in str(exc.value)
    assert "401" in str(exc.value)
