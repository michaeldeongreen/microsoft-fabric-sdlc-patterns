"""Trusted provisioning stages and create-only GitHub variable persistence."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

import bootstrap_dev_connections as bootstrap
from test_connection_provisioning import GROUP, NOTEBOOK, REFRESH, WORKSPACE, fake_client

VALUES = {bootstrap.NOTEBOOK_CONNECTION_ENV: NOTEBOOK, bootstrap.REFRESH_CONNECTION_ENV: REFRESH}


class FakeGitHub(bootstrap.GitHubVariables):
    def __init__(self, values: dict[str, str] | None = None) -> None:
        super().__init__("owner/sample", "Test", "unit-test-token-never-log")
        self.values = dict(values or {})
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def request(self, method: str, suffix: str = "", body: dict[str, str] | None = None) -> dict[str, object]:
        self.calls.append((method, suffix, body))
        if method == "GET" and suffix == "":
            return {"name": "Test"}
        if method == "GET":
            key = suffix.rsplit("/", 1)[1]
            if key not in self.values:
                raise bootstrap.GitHubVariableError("Not found", 404)
            return {"name": key, "value": self.values[key]}
        assert method == "POST" and suffix == "/variables" and body is not None
        self.values[body["name"]] = body["value"]
        return {}


def test_save_once_and_repeat_with_zero_writes() -> None:
    github = FakeGitHub()
    github.persist(VALUES)
    assert github.values == VALUES
    assert len([call for call in github.calls if call[0] == "POST"]) == 2
    github.calls.clear()
    github.persist(VALUES)
    assert all(call[0] == "GET" for call in github.calls)


def test_mismatch_detected_before_any_variable_write() -> None:
    github = FakeGitHub({bootstrap.REFRESH_CONNECTION_ENV: GROUP})
    with pytest.raises(bootstrap.BootstrapError, match="different connection"):
        github.persist(VALUES)
    assert all(call[0] == "GET" for call in github.calls)


def test_partial_write_retries_without_overwriting() -> None:
    github = FakeGitHub({bootstrap.NOTEBOOK_CONNECTION_ENV: NOTEBOOK})
    github.persist(VALUES)
    assert [call[2]["name"] for call in github.calls if call[0] == "POST"] == [bootstrap.REFRESH_CONNECTION_ENV]


@pytest.mark.parametrize("status", [409, 422])
def test_concurrent_create_is_read_back_and_compared(status: int) -> None:
    github = FakeGitHub()
    original = github.request

    def request(method: str, suffix: str = "", body: dict[str, str] | None = None) -> dict[str, object]:
        if method == "POST":
            assert body is not None
            github.values[body["name"]] = body["value"]
            raise bootstrap.GitHubVariableError("Concurrent create", status)
        return original(method, suffix, body)

    github.request = request
    github.persist(VALUES)
    assert github.values == VALUES


@pytest.fixture()
def actions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key, value in {
        "GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/test", "ENVIRONMENT": "Test",
        "GITHUB_REPOSITORY": "owner/sample", "FABRIC_WORKSPACE_ID": WORKSPACE,
        bootstrap.GROUP_ENV: GROUP,
    }.items():
        monkeypatch.setenv(key, value)
    for key in (*bootstrap.CONNECTION_KEYS, "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(key, raising=False)
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return output


def test_provision_has_no_model_or_pipeline_prerequisite(actions: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = fake_client()
    monkeypatch.setattr(bootstrap, "actions_client", Mock(return_value=client))
    bootstrap.main(["--operation", "provision"])
    assert {line.split("=", 1)[0]: line.split("=", 1)[1] for line in actions.read_text(encoding="utf-8").splitlines()} == VALUES
    assert all(client.roles[identifier][0]["role"] == "Owner" for identifier in VALUES.values())


def test_failed_owner_sharing_exports_no_ids(actions: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "actions_client", Mock(return_value=fake_client()))
    monkeypatch.setattr(bootstrap, "grant_connection_group_owner", Mock(side_effect=ValueError("Sharing denied")))
    with pytest.raises(SystemExit):
        bootstrap.main(["--operation", "provision"])
    assert not actions.exists()


@pytest.mark.parametrize("key,value", [
    (bootstrap.GROUP_ENV, ""), (bootstrap.GROUP_ENV, "bad"),
    ("GITHUB_REF", "refs/heads/feature/untrusted"), ("GITHUB_ACTIONS", "false"),
    (bootstrap.GROUP_ENV, WORKSPACE),
])
def test_invalid_configuration_stops_before_authentication(
    actions: Path, monkeypatch: pytest.MonkeyPatch, key: str, value: str,
) -> None:
    monkeypatch.setenv(key, value)
    auth = Mock()
    monkeypatch.setattr(bootstrap, "actions_client", auth)
    with pytest.raises(SystemExit):
        bootstrap.main(["--operation", "provision"])
    auth.assert_not_called()
    assert not actions.exists()


def test_legacy_recovery_restricted_to_dev(actions: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = Mock()
    monkeypatch.setattr(bootstrap, "actions_client", auth)
    with pytest.raises(SystemExit):
        bootstrap.main(["--operation", "share-existing"])
    auth.assert_not_called()


@pytest.mark.parametrize("ref,environment", [
    ("refs/heads/test", "Prod"), ("refs/heads/main", "Test"),
    ("refs/heads/dev", "Test"), ("refs/heads/test", ""),
])
def test_selected_environment_mismatch_stops_before_api_access(
    actions: Path, monkeypatch: pytest.MonkeyPatch, ref: str, environment: str,
) -> None:
    monkeypatch.setenv("GITHUB_REF", ref)
    monkeypatch.setenv("ENVIRONMENT", environment)
    github = Mock()
    auth = Mock()
    monkeypatch.setattr(bootstrap, "GitHubVariables", github)
    monkeypatch.setattr(bootstrap, "actions_client", auth)
    with pytest.raises(SystemExit):
        bootstrap.main(["--operation", "preflight"])
    github.assert_not_called()
    auth.assert_not_called()
    assert not actions.exists()


@pytest.mark.parametrize("ref,environment", [
    ("refs/heads/test", "Test"), ("refs/heads/main", "Prod"),
])
def test_release_targets_the_selected_stage(
    actions: Path, monkeypatch: pytest.MonkeyPatch, ref: str, environment: str,
) -> None:
    monkeypatch.setenv("GITHUB_REF", ref)
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv(bootstrap.TOKEN_ENV, "unit-test-token-never-log")
    github = Mock()
    github.preflight.return_value = {}
    factory = Mock(return_value=github)
    monkeypatch.setattr(bootstrap, "GitHubVariables", factory)
    bootstrap.main(["--operation", "preflight"])
    factory.assert_called_once_with("owner/sample", environment, "unit-test-token-never-log")


def test_standalone_setup_derives_environment_only_when_key_is_absent(
    actions: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENVIRONMENT")
    github = Mock()
    github.preflight.return_value = {}
    factory = Mock(return_value=github)
    monkeypatch.setattr(bootstrap, "GitHubVariables", factory)
    bootstrap.main(["--operation", "preflight"])
    assert factory.call_args.args[1] == "Test"


def test_persistence_stage_never_authenticates_to_fabric(actions: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    github = FakeGitHub()
    monkeypatch.setattr(bootstrap, "GitHubVariables", Mock(return_value=github))
    auth = Mock()
    monkeypatch.setattr(bootstrap, "actions_client", auth)
    for key, value in VALUES.items():
        monkeypatch.setenv(key, value)
    bootstrap.main(["--operation", "persist"])
    assert github.values == VALUES
    auth.assert_not_called()


def test_preflight_permission_failure_prevents_fabric_stage(actions: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    github = Mock()
    github.preflight.side_effect = bootstrap.GitHubVariableError("Denied", 403)
    monkeypatch.setattr(bootstrap, "GitHubVariables", Mock(return_value=github))
    auth = Mock()
    monkeypatch.setattr(bootstrap, "actions_client", auth)
    with pytest.raises(SystemExit):
        bootstrap.main(["--operation", "preflight"])
    auth.assert_not_called()


def run_release_setup(
    output_root: Path, monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for operation in ("preflight", "provision", "persist"):
        output = output_root.with_name(f"{output_root.name}-{operation}")
        with monkeypatch.context() as step:
            step.setenv("GITHUB_OUTPUT", str(output))
            for key in bootstrap.CONNECTION_KEYS:
                step.delenv(key, raising=False)
            for key, value in values.items():
                step.setenv(key, value)
            step.delenv("AZURE_CLIENT_SECRET", raising=False)
            step.delenv(bootstrap.TOKEN_ENV, raising=False)
            if operation == "provision":
                step.setenv("AZURE_CLIENT_SECRET", "unit-test-sp-secret")
            else:
                step.setenv(bootstrap.TOKEN_ENV, "unit-test-token-never-log")
            bootstrap.main(["--operation", operation])
        if operation != "persist":
            values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
    return values


def test_cold_first_release_and_repeat_resolve_and_persist_in_same_run(
    actions: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    github = FakeGitHub()
    client = fake_client()

    def fabric_factory(environ: Mapping[str, str]) -> Mock:
        assert bootstrap.TOKEN_ENV not in environ
        return client

    def github_factory(repository: str, environment: str, token: str) -> FakeGitHub:
        assert "AZURE_CLIENT_SECRET" not in os.environ
        assert environment == "Test"
        return github

    monkeypatch.setattr(bootstrap, "actions_client", fabric_factory)
    monkeypatch.setattr(bootstrap, "GitHubVariables", github_factory)
    assert github.values == {} and client.connections == {}
    resolved = run_release_setup(actions, monkeypatch)
    assert resolved == VALUES
    assert github.values == VALUES
    assert all(client.roles[identifier][0]["role"] == "Owner" for identifier in VALUES.values())
    client.request.reset_mock()
    github.calls.clear()
    assert run_release_setup(actions.with_name("repeat"), monkeypatch) == resolved
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)
    assert all(method == "GET" for method, _, _ in github.calls)


@pytest.mark.parametrize("failure", ["owner", "persistence"])
def test_failed_release_setup_prevents_publication(
    actions: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    github = FakeGitHub()
    monkeypatch.setattr(bootstrap, "GitHubVariables", Mock(return_value=github))
    monkeypatch.setattr(bootstrap, "actions_client", Mock(return_value=fake_client()))
    if failure == "owner":
        monkeypatch.setattr(bootstrap, "grant_connection_group_owner", Mock(side_effect=ValueError("Owner grant denied")))
    else:
        github.persist = Mock(side_effect=bootstrap.GitHubVariableError("Variable write denied", 403))
    publish = Mock()
    with pytest.raises(SystemExit):
        resolved = run_release_setup(actions, monkeypatch)
        publish(resolved)
    publish.assert_not_called()


def test_http_client_uses_fixed_host_and_never_logs_token(capsys: pytest.CaptureFixture[str]) -> None:
    token = "unit-test-only-token"
    github = bootstrap.GitHubVariables("owner/sample", "Test", token)
    github.opener = Mock()
    github.opener.open.return_value = BytesIO(json.dumps({"name": "Test"}).encode("utf-8"))
    assert github.request("GET") == {"name": "Test"}
    request = github.opener.open.call_args.args[0]
    assert request.full_url == "https://api.github.com/repos/owner/sample/environments/Test"
    assert request.get_header("Authorization") == f"Bearer {token}"
    assert token not in capsys.readouterr().out


@pytest.mark.parametrize("method,suffix,body", [
    ("PATCH", "/variables/NOTEBOOK_CONNECTION_ID", {"name": "NOTEBOOK_CONNECTION_ID", "value": NOTEBOOK}),
    ("POST", "", {"name": "NOTEBOOK_CONNECTION_ID", "value": NOTEBOOK}),
    ("POST", "/variables", {"name": "UNRELATED", "value": NOTEBOOK}),
    ("GET", "/secrets", None),
])
def test_writer_cannot_manage_unrelated_resources(method: str, suffix: str, body: dict[str, str] | None) -> None:
    github = bootstrap.GitHubVariables("owner/sample", "Test", "test-token")
    github.opener = Mock()
    with pytest.raises(bootstrap.BootstrapError):
        github.request(method, suffix, body)
    github.opener.open.assert_not_called()


@pytest.mark.parametrize("failure", [
    HTTPError("https://api.github.com/", 403, "unit-test-token-never-log", {}, BytesIO(b"sensitive response")),
    URLError("unit-test-token-never-log"),
])
def test_http_failures_suppress_response_and_token(failure: Exception) -> None:
    github = bootstrap.GitHubVariables("owner/sample", "Test", "unit-test-token-never-log")
    github.opener = Mock()
    github.opener.open.side_effect = failure
    with pytest.raises(bootstrap.GitHubVariableError) as result:
        github.request("GET")
    assert "unit-test-token-never-log" not in str(result.value)
    assert "sensitive response" not in str(result.value)


def test_missing_persistence_is_not_a_successful_fallback() -> None:
    github = FakeGitHub()
    original = github.request

    def request(method: str, suffix: str = "", body: dict[str, str] | None = None) -> dict[str, object]:
        return {} if method == "POST" else original(method, suffix, body)

    github.request = request
    with pytest.raises(bootstrap.BootstrapError, match="not confirmed"):
        github.persist(VALUES)


def test_wrong_environment_metadata_fails_before_create() -> None:
    github = FakeGitHub()
    github.request = Mock(return_value={"name": "Prod"})
    with pytest.raises(bootstrap.BootstrapError, match="different or malformed"):
        github.preflight()


@pytest.mark.parametrize("token", ["", "bad\nsecret", " bad ", "bad\r\nHeader: secret"])
def test_invalid_token_is_rejected_without_revealing_its_value(token: str) -> None:
    with pytest.raises(bootstrap.BootstrapError) as result:
        bootstrap.GitHubVariables("owner/sample", "Test", token)
    assert "bad" not in str(result.value)
    assert "secret" not in str(result.value)
