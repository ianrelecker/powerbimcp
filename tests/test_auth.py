from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from powerbi_mcp.config import FABRIC_RESOURCE, POWERBI_RESOURCE
from powerbi_mcp.microsoft_auth import MicrosoftAuthService, decode_id_claims

from .conftest import make_jwt


def test_decode_id_claims_extracts_payload() -> None:
    token = make_jwt(
        {
            "name": "A User",
            "preferred_username": "user@example.com",
            "oid": "oid-123",
            "tid": "tid-456",
        }
    )

    claims = decode_id_claims(token)
    assert claims == {
        "name": "A User",
        "preferred_username": "user@example.com",
        "oid": "oid-123",
        "tid": "tid-456",
    }


@pytest.mark.anyio
async def test_callback_rejects_invalid_state(config_factory) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    auth = MicrosoftAuthService(config_factory(), client)
    auth.build_authorization_url()

    with pytest.raises(RuntimeError, match="state was invalid"):
        await auth.handle_authorization_code_callback(
            code="auth-code",
            state="wrong-state",
            error=None,
            errorDescription=None,
        )

    await client.aclose()


@pytest.mark.anyio
async def test_status_reports_missing_scopes(config_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = dict(parse_qs(request.content.decode("utf-8")))
        scope = body.get("scope", [""])[0]
        if "api.fabric.microsoft.com" in scope:
            return httpx.Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "Fabric consent missing",
                },
            )

        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "scope": "Dashboard.Read.All",
                "id_token": make_jwt({"preferred_username": "user@example.com"}),
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    auth = MicrosoftAuthService(config_factory(), client)
    state = parse_qs(urlparse(auth.build_authorization_url()).query)["state"][0]

    await auth.handle_authorization_code_callback(
        code="auth-code",
        state=state,
        error=None,
        errorDescription=None,
    )

    status = await auth.get_status()
    assert status.connected is True
    assert "Dashboard.Read.All" in status.grantedScopes
    assert "https://analysis.windows.net/powerbi/api/Workspace.Read.All" in status.missingScopes
    assert "https://analysis.windows.net/powerbi/api/Dataset.ReadWrite.All" in status.missingScopes
    assert "https://api.fabric.microsoft.com/Workspace.Read.All" in status.missingScopes
    assert "https://api.fabric.microsoft.com/SemanticModel.Read.All" in status.missingScopes
    assert {resource.resource for resource in status.resourceStatuses} == {
        POWERBI_RESOURCE,
        FABRIC_RESOURCE,
    }

    await client.aclose()


@pytest.mark.anyio
async def test_refresh_token_can_fetch_distinct_powerbi_and_fabric_tokens(config_factory) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = dict(parse_qs(request.content.decode("utf-8")))
        scope = body.get("scope", [""])[0]
        grant_type = body.get("grant_type", [""])[0]
        requests.append(scope)

        if grant_type == "authorization_code":
            return httpx.Response(
                200,
                json={
                    "access_token": "powerbi-token-1",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": "Workspace.Read.All Dashboard.Read.All Report.Read.All Dataset.ReadWrite.All",
                    "id_token": make_jwt({"preferred_username": "user@example.com"}),
                },
            )

        if "api.fabric.microsoft.com" in scope:
            return httpx.Response(
                200,
                json={
                    "access_token": "fabric-token",
                    "expires_in": 3600,
                    "scope": "Workspace.Read.All SemanticModel.Read.All",
                },
            )

        return httpx.Response(
            200,
            json={
                "access_token": "powerbi-token-2",
                "expires_in": 3600,
                "scope": "Workspace.Read.All Dashboard.Read.All Report.Read.All Dataset.ReadWrite.All",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    auth = MicrosoftAuthService(config_factory(), client)
    state = parse_qs(urlparse(auth.build_authorization_url()).query)["state"][0]

    await auth.handle_authorization_code_callback(
        code="auth-code",
        state=state,
        error=None,
        errorDescription=None,
    )

    assert await auth.get_access_token(POWERBI_RESOURCE) == "powerbi-token-1"
    assert await auth.get_access_token(FABRIC_RESOURCE) == "fabric-token"
    assert any("analysis.windows.net" in scope for scope in requests)
    assert any("api.fabric.microsoft.com" in scope for scope in requests)

    status = await auth.get_status()
    assert status.missingScopes == []

    await client.aclose()
