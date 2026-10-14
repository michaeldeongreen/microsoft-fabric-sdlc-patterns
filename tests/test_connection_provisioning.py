"""Connection-only WI provisioning never needs workspace-ACL management."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import fabric_connections as fabric

WORKSPACE = "11111111-aaaa-4111-8111-111111111111"
GROUP = "22222222-bbbb-4222-8222-222222222222"
NOTEBOOK = "33333333-cccc-4333-8333-333333333333"
REFRESH = "44444444-dddd-4444-8444-444444444444"
IDENTITY = "55555555-eeee-4555-8555-555555555555"


def connection(kind: str, identifier: str, stage: str = "Test") -> dict[str, object]:
    suffix = "Notebook" if kind == "Notebook" else "SemanticModelRefresh"
    return {
        "id": identifier, "displayName": f"Patterns-{stage}-{suffix}-{WORKSPACE}",
        "connectivityType": "ShareableCloud",
        "connectionDetails": {"type": kind, "creationMethod": f"{kind}.Actions"},
        "credentialDetails": {"credentialType": "WorkspaceIdentity"},
        "allowUsageInUserControlledCode": False,
    }


def fake_client() -> Mock:
    client = Mock(spec=fabric.FabricRestClient)
    client.connections = {}
    client.roles = {NOTEBOOK: [], REFRESH: []}
    client.has_identity = True

    def request(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        if method == "GET" and path == f"/workspaces/{WORKSPACE}":
            return {"id": WORKSPACE, "workspaceIdentity": (
                {"applicationId": IDENTITY, "servicePrincipalId": IDENTITY} if client.has_identity else None
            )}
        if method == "GET" and path.startswith("/connections/"):
            return client.connections[path.rsplit("/", 1)[1]]
        if method == "POST" and path == "/connections":
            assert body is not None
            kind = body["connectionDetails"]["type"]
            identifier = NOTEBOOK if kind == "Notebook" else REFRESH
            item = connection(kind, identifier)
            item["displayName"] = body["displayName"]
            client.connections[identifier] = item
            return item
        if "/roleAssignments" in path:
            identifier = path.split("/")[2]
            assert body is not None
            if method == "POST":
                client.roles[identifier] = [{"id": GROUP, **body}]
            elif method == "PATCH":
                client.roles[identifier][0]["role"] = body["role"]
            else:
                raise AssertionError((method, path))
            return {}
        raise AssertionError((method, path))

    def listing(path: str) -> list[dict[str, object]]:
        if path == "/connections":
            return list(client.connections.values())
        if path.startswith("/connections/supportedConnectionTypes"):
            return [{
                "type": kind, "supportedCredentialTypes": ["WorkspaceIdentity"],
                "creationMethods": [{"name": f"{kind}.Actions", "parameters": []}],
            } for kind in ("Notebook", "PowerBIDatasets")]
        if path.endswith("/roleAssignments") and path.startswith("/connections/"):
            return client.roles[path.split("/")[2]]
        raise AssertionError(f"Unexpected collection (workspace ACLs are not permitted): {path}")

    client.request.side_effect = request
    client.list.side_effect = listing
    return client


def provision(client: Mock) -> dict[str, str]:
    return fabric.provision_wi_connections(client, WORKSPACE, "Test")


def test_creates_two_named_wi_connections_without_workspace_acl_calls() -> None:
    client = fake_client()
    assert provision(client) == {
        fabric.NOTEBOOK_CONNECTION_ENV: NOTEBOOK, fabric.REFRESH_CONNECTION_ENV: REFRESH,
    }
    writes = [call.args for call in client.request.call_args_list if call.args[0] != "GET"]
    assert len(writes) == 2
    for method, path, body in writes:
        assert (method, path) == ("POST", "/connections")
        assert body["credentialDetails"]["credentials"] == {"credentialType": "WorkspaceIdentity"}
        assert body["allowUsageInUserControlledCode"] is False
        assert body["displayName"].startswith("Patterns-Test-")
        assert body["displayName"].endswith(WORKSPACE)


def test_repeat_provision_and_group_owner_are_idempotent() -> None:
    client = fake_client()
    values = provision(client)
    fabric.grant_connection_group_owner(client, list(values.values()), GROUP)
    client.request.reset_mock()
    assert provision(client) == values
    fabric.grant_connection_group_owner(client, list(values.values()), GROUP)
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)


def test_preexisting_ids_allow_intentional_human_names() -> None:
    client = fake_client()
    for kind, identifier in (("Notebook", NOTEBOOK), ("PowerBIDatasets", REFRESH)):
        client.connections[identifier] = {**connection(kind, identifier), "displayName": "Explicit human name"}
    result = fabric.provision_wi_connections(
        client, WORKSPACE, "Test", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
    )
    assert set(result.values()) == {NOTEBOOK, REFRESH}
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)


def test_missing_wi_fails_without_creating_or_elevating_anything() -> None:
    client = fake_client()
    client.has_identity = False
    with pytest.raises(fabric.FabricConnectionError, match="Create the target Workspace Identity"):
        provision(client)
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)
    client.list.assert_not_called()


@pytest.mark.parametrize("change", [
    {"credentialDetails": {"credentialType": "ServicePrincipal"}},
    {"connectionDetails": {"type": "Unrelated"}},
    {"allowUsageInUserControlledCode": True},
])
def test_wrong_existing_configuration_never_silently_repaired(change: dict[str, object]) -> None:
    client = fake_client()
    client.connections[NOTEBOOK] = {**connection("Notebook", NOTEBOOK), **change}
    with pytest.raises(fabric.FabricConnectionError):
        provision(client)
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)


@pytest.mark.parametrize("role", ["User", "UserWithReshare", "Owner"])
def test_group_is_upgraded_to_owner_not_left_with_use_only(role: str) -> None:
    client = fake_client()
    for identifier in (NOTEBOOK, REFRESH):
        client.roles[identifier] = [{"id": GROUP, "principal": {"id": GROUP, "type": "Group"}, "role": role}]
    fabric.grant_connection_group_owner(client, [NOTEBOOK, REFRESH], GROUP)
    assert all(client.roles[identifier][0]["role"] == "Owner" for identifier in (NOTEBOOK, REFRESH))
    writes = [call.args for call in client.request.call_args_list]
    assert len(writes) == (0 if role == "Owner" else 2)
    assert all(args[0] == "PATCH" and args[2] == {"role": "Owner"} for args in writes)


@pytest.mark.parametrize("bad", [
    {"id": GROUP, "principal": {"id": GROUP, "type": "User"}, "role": "User"},
    {"id": GROUP, "principal": {"id": GROUP, "type": "Group"}, "role": "Unknown"},
    {"id": "invalid", "principal": {"id": GROUP, "type": "Group"}, "role": "Owner"},
])
def test_both_acl_preflights_finish_before_any_grant(bad: dict[str, object]) -> None:
    client = fake_client()
    client.roles[REFRESH] = [bad]
    with pytest.raises(fabric.FabricConnectionError):
        fabric.grant_connection_group_owner(client, [NOTEBOOK, REFRESH], GROUP)
    client.request.assert_not_called()


def test_unconfirmed_role_assignment_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fake_client()
    client.request.side_effect = None
    client.request.return_value = {}
    monkeypatch.setattr(fabric.time, "sleep", Mock())
    with pytest.raises(fabric.FabricConnectionError, match="not confirmed"):
        fabric.grant_connection_group_owner(client, [NOTEBOOK, REFRESH], GROUP)


@pytest.mark.parametrize("group", ["bad", ""])
def test_group_guid_rejected_instead_of_sharing_wrong_principal(group: str) -> None:
    client = fake_client()
    with pytest.raises(fabric.FabricConnectionError):
        fabric.grant_connection_group_owner(client, [NOTEBOOK, REFRESH], group)
    client.request.assert_not_called()


def test_duplicate_group_metadata_stops_before_writes() -> None:
    client = fake_client()
    assignment = {"id": GROUP, "principal": {"id": GROUP, "type": "Group"}, "role": "Owner"}
    client.roles[REFRESH] = [assignment, assignment]
    with pytest.raises(fabric.FabricConnectionError, match="Duplicate"):
        fabric.grant_connection_group_owner(client, [NOTEBOOK, REFRESH], GROUP)
    client.request.assert_not_called()


def test_inaccessible_duplicate_name_is_not_replaced() -> None:
    client = fake_client()
    original = client.request.side_effect

    def request(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        if method == "POST" and path == "/connections":
            raise fabric.FabricRestError("Duplicate", error_code="DuplicateConnectionName")
        return original(method, path, body)

    client.request.side_effect = request
    with pytest.raises(fabric.FabricConnectionError, match="inaccessible"):
        provision(client)
    assert len([call for call in client.request.call_args_list if call.args[0] == "POST"]) == 1
