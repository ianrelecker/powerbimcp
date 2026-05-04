from __future__ import annotations

import sys
from pathlib import Path

import pytest

from powerbi_mcp.config import POWERBI_RESOURCE, XMLA_WRITE_CONFIRMATION
from powerbi_mcp.models import (
    SemanticModelInfo,
    SemanticModelListResult,
    SemanticModelResult,
    StoredResourceToken,
    WorkspaceInfo,
    WorkspaceResult,
)
from powerbi_mcp.xmla import PowerBIXMLAClient, XMLABridgeRunner


class StaticAuthService:
    async def get_access_token_record(self, resource: str = POWERBI_RESOURCE) -> StoredResourceToken:
        assert resource == POWERBI_RESOURCE
        return StoredResourceToken(
            accessToken="powerbi-token",
            expiresAt=4_102_444_800_000,
            scope="Dataset.ReadWrite.All",
            updatedAt=1,
        )


class StaticPowerBIClient:
    async def get_workspace(self, *, workspaceId: str) -> WorkspaceResult:
        return WorkspaceResult(
            workspace=WorkspaceInfo(
                id=workspaceId,
                name="Sales Workspace",
                type="Workspace",
            )
        )


class StaticFabricClient:
    async def get_semantic_model(
        self,
        *,
        workspaceId: str,
        semanticModelId: str,
    ) -> SemanticModelResult:
        return SemanticModelResult(
            workspaceId=workspaceId,
            semanticModel=SemanticModelInfo(
                id=semanticModelId,
                displayName="Sales Model",
                type="SemanticModel",
                workspaceId=workspaceId,
            ),
        )

    async def list_semantic_models(self, *, workspaceId: str, **kwargs) -> SemanticModelListResult:
        return SemanticModelListResult(
            workspaceId=workspaceId,
            semanticModels=[
                SemanticModelInfo(
                    id="semantic-1",
                    displayName="Sales Model",
                    type="SemanticModel",
                    workspaceId=workspaceId,
                )
            ],
        )


class RecordingBridgeRunner:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_first = fail_first

    async def run(self, payload, *, access_token: str, expires_at: int):
        assert access_token == "powerbi-token"
        self.calls.append(payload)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("catalog not found")
        if payload["command"] == "query":
            return {
                "columns": ["Metric"],
                "rows": [{"Metric": 1}],
                "rowCount": 1,
                "truncated": False,
            }
        if payload["command"] == "execute":
            return {
                "executed": True,
                "messages": ["ok"],
                "results": [{"messageCount": 1}],
            }
        return {"state": "Open"}


@pytest.mark.anyio
async def test_xmla_attach_builds_urls_and_retries_duplicate_catalog_form(config_factory) -> None:
    bridge = RecordingBridgeRunner(fail_first=True)
    xmla = PowerBIXMLAClient(
        config_factory(xmlaTenantAlias="contoso.com"),
        StaticAuthService(),
        StaticPowerBIClient(),
        StaticFabricClient(),
        bridge,
    )

    attach = await xmla.attach(
        workspaceId="workspace-1",
        semanticModelName="Sales Model",
    )

    assert attach.serverUrl == "powerbi://api.powerbi.com/v1.0/contoso.com/Sales%20Workspace"
    assert attach.initialCatalog == "Sales Model"
    assert attach.validated is True
    assert attach.effectiveInitialCatalog == "Sales Model - semantic-1"
    assert bridge.calls[0]["initialCatalog"] == "Sales Model"
    assert bridge.calls[1]["initialCatalog"] == "Sales Model - semantic-1"


@pytest.mark.anyio
async def test_xmla_query_returns_rows(config_factory) -> None:
    bridge = RecordingBridgeRunner()
    xmla = PowerBIXMLAClient(
        config_factory(),
        StaticAuthService(),
        StaticPowerBIClient(),
        StaticFabricClient(),
        bridge,
    )

    result = await xmla.query(
        workspaceId="workspace-1",
        semanticModelId="semantic-1",
        query="EVALUATE ROW(\"Metric\", 1)",
        queryType="dax",
    )

    assert result.rows == [{"Metric": 1}]
    assert bridge.calls[-1]["query"] == "EVALUATE ROW(\"Metric\", 1)"


@pytest.mark.anyio
async def test_xmla_execute_requires_env_opt_in_and_confirmation(config_factory) -> None:
    xmla = PowerBIXMLAClient(
        config_factory(xmlaAllowWrites=False),
        StaticAuthService(),
        StaticPowerBIClient(),
        StaticFabricClient(),
        RecordingBridgeRunner(),
    )

    with pytest.raises(RuntimeError, match="XMLA writes are disabled"):
        await xmla.execute(
            workspaceId="workspace-1",
            semanticModelId="semantic-1",
            commandText="<Alter />",
            confirmation=XMLA_WRITE_CONFIRMATION,
        )

    xmla = PowerBIXMLAClient(
        config_factory(xmlaAllowWrites=True),
        StaticAuthService(),
        StaticPowerBIClient(),
        StaticFabricClient(),
        RecordingBridgeRunner(),
    )
    with pytest.raises(RuntimeError, match="require confirmation"):
        await xmla.execute(
            workspaceId="workspace-1",
            semanticModelId="semantic-1",
            commandText="<Alter />",
        )


@pytest.mark.anyio
async def test_xmla_execute_runs_when_confirmed(config_factory) -> None:
    bridge = RecordingBridgeRunner()
    xmla = PowerBIXMLAClient(
        config_factory(xmlaAllowWrites=True),
        StaticAuthService(),
        StaticPowerBIClient(),
        StaticFabricClient(),
        bridge,
    )

    result = await xmla.execute(
        workspaceId="workspace-1",
        semanticModelId="semantic-1",
        commandText="<Alter />",
        confirmation=XMLA_WRITE_CONFIRMATION,
    )

    assert result.executed is True
    assert result.messages == ["ok"]
    assert bridge.calls[-1]["commandText"] == "<Alter />"


@pytest.mark.anyio
async def test_xmla_bridge_errors_redact_access_tokens() -> None:
    runner = XMLABridgeRunner(Path("unused"))
    runner._command = lambda: [  # type: ignore[method-assign]
        sys.executable,
        "-c",
        "import sys; sys.stderr.write(sys.stdin.read()); sys.exit(1)",
    ]

    with pytest.raises(RuntimeError) as error:
        await runner.run(
            {"command": "attach"},
            access_token="secret-token",
            expires_at=1,
        )

    assert "secret-token" not in str(error.value)
    assert "[redacted]" in str(error.value)
