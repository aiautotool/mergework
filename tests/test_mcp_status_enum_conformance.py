from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import create_schema, session_scope
from app.ledger.service import ensure_genesis
from app.main import create_app


def _client(sqlite_url: str) -> TestClient:
    create_schema(sqlite_url)
    with session_scope(sqlite_url) as session:
        ensure_genesis(session)
    return TestClient(create_app(database_url=sqlite_url, webhook_secret="secret"))


def _call_list_bounties(client: TestClient, arguments: dict[str, object]) -> dict[str, object]:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_bounties", "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()


def test_mcp_list_bounties_status_runtime_matches_advertised_enum(sqlite_url: str) -> None:
    client = _client(sqlite_url)

    tools_response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    ).json()
    list_bounties = next(
        tool for tool in tools_response["result"]["tools"] if tool["name"] == "list_bounties"
    )
    advertised_statuses = list_bounties["inputSchema"]["properties"]["status"]["enum"]
    assert advertised_statuses == ["open", "paid", "closed"]

    for status in advertised_statuses:
        result = _call_list_bounties(client, {"status": status})
        assert "result" in result

    omitted = _call_list_bounties(client, {})
    assert "result" in omitted


@pytest.mark.parametrize("status", ["OPEN", " open ", "Paid", "", None])
def test_mcp_list_bounties_rejects_status_values_outside_schema_enum(
    sqlite_url: str, status: object
) -> None:
    client = _client(sqlite_url)

    result = _call_list_bounties(client, {"status": status})

    assert result["error"]["code"] == -32602
    assert result["error"]["message"] == "invalid tool arguments"
    assert result["error"]["data"]["code"] == "invalid_argument"
    assert result["error"]["data"]["tool"] == "list_bounties"
    assert result["error"]["data"]["field"] == "status"
