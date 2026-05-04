from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from powerbi_mcp.models import (
    AccountInfo,
    AuthStatusResult,
    DashboardInfo,
    DashboardListResult,
    DatasetInfo,
    MicrosoftConnectionStatus,
    ResourceScopeStatus,
    SemanticModelInfo,
    SemanticModelListResult,
    TileInfo,
    TileListResult,
    XmlaAttachResult,
    XmlaQueryResult,
)
from powerbi_mcp.server import RuntimeServices, _can_bind_localhost, create_mcp_server


class StubAuthService:
    async def get_status(self) -> MicrosoftConnectionStatus:
        return MicrosoftConnectionStatus(
            connected=True,
            account=AccountInfo(preferredUsername="user@example.com"),
            expiresAt=1712345678901,
            knownWorkspaces=["Sales Workspace"],
            resourceStatuses=[
                ResourceScopeStatus(
                    resource="powerbi",
                    connected=True,
                    expiresAt=1712345678901,
                    requiredScopes=[
                        "https://analysis.windows.net/powerbi/api/Dataset.ReadWrite.All"
                    ],
                    grantedScopes=[
                        "Dataset.ReadWrite.All"
                    ],
                ),
                ResourceScopeStatus(
                    resource="fabric",
                    connected=True,
                    expiresAt=1712345678901,
                    requiredScopes=[
                        "https://api.fabric.microsoft.com/Workspace.Read.All",
                        "https://api.fabric.microsoft.com/SemanticModel.Read.All"
                    ],
                    grantedScopes=[
                        "Workspace.Read.All",
                        "SemanticModel.Read.All"
                    ],
                ),
            ],
        )


class StubPowerBIClient:
    def __init__(self) -> None:
        self.last_workspace_id: str | None = None

    async def list_workspaces(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def get_workspace(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def list_dashboards(self, **kwargs) -> DashboardListResult:
        self.last_workspace_id = kwargs["workspaceId"]
        return DashboardListResult(
            workspaceId=kwargs["workspaceId"],
            dashboards=[
                DashboardInfo(id="dashboard-1", displayName="Sales Dashboard")
            ],
        )

    async def get_dashboard(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def list_tiles(self, **kwargs) -> TileListResult:
        return TileListResult(
            workspaceId=kwargs["workspaceId"],
            dashboardId=kwargs["dashboardId"],
            tiles=[
                TileInfo(
                    id="tile-1",
                    title="Revenue",
                    reportId="report-1",
                    datasetId="dataset-1",
                )
            ],
        )

    async def get_tile(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def dashboard_summary(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def search_dashboards(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def list_reports(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def get_report(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def list_datasets(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def get_dataset(self, **kwargs):
        return {"workspaceId": kwargs["workspaceId"], "dataset": DatasetInfo(id=kwargs["datasetId"], name="Dataset")}

    async def list_dataset_datasources(self, **kwargs):
        raise AssertionError("Not expected in this test")

    async def get_refresh_history(self, **kwargs):
        raise AssertionError("Not expected in this test")


class StubFabricClient:
    async def list_semantic_models(self, **kwargs) -> SemanticModelListResult:
        return SemanticModelListResult(
            workspaceId=kwargs["workspaceId"],
            semanticModels=[
                SemanticModelInfo(
                    id="semantic-1",
                    displayName="Sales Model",
                    type="SemanticModel",
                    workspaceId=kwargs["workspaceId"],
                )
            ],
        )

    async def get_semantic_model(self, **kwargs):
        raise AssertionError("Not expected in this test")


class StubXMLAClient:
    async def attach(self, **kwargs) -> XmlaAttachResult:
        return XmlaAttachResult(
            workspaceId=kwargs["workspaceId"],
            workspaceName="Sales Workspace",
            semanticModelId=kwargs["semanticModelId"] or "semantic-1",
            semanticModelName=kwargs["semanticModelName"] or "Sales Model",
            tenantAlias=kwargs["tenantAlias"] or "myorg",
            serverUrl="powerbi://api.powerbi.com/v1.0/myorg/Sales%20Workspace",
            initialCatalog=kwargs["semanticModelName"] or "Sales Model",
            alternateServerUrl=None,
            alternateInitialCatalog=None,
            effectiveServerUrl="powerbi://api.powerbi.com/v1.0/myorg/Sales%20Workspace",
            effectiveInitialCatalog=kwargs["semanticModelName"] or "Sales Model",
            validated=True,
            writeEnabled=False,
            requirements=[],
        )

    async def query(self, **kwargs) -> XmlaQueryResult:
        attach = await self.attach(**kwargs)
        return XmlaQueryResult(
            attach=attach,
            queryType=kwargs["queryType"],
            columns=["Metric"],
            rows=[{"Metric": 1}],
            rowCount=1,
            truncated=False,
        )

    async def execute(self, **kwargs):
        raise AssertionError("Not expected in this test")


@pytest.mark.anyio
async def test_mcp_server_exposes_expected_tools_and_structured_outputs(config_factory) -> None:
    powerbi = StubPowerBIClient()
    http_client = httpx.AsyncClient()
    runtime = RuntimeServices(
        config=config_factory(localBaseUrl="http://localhost:8787"),
        microsoft_auth=StubAuthService(),
        powerbi=powerbi,
        fabric=StubFabricClient(),
        xmla=StubXMLAClient(),
        http_client=http_client,
        owns_http_client=False,
        start_helper_server=False,
    )
    server = create_mcp_server(runtime)

    async with create_connected_server_and_client_session(server, raise_exceptions=True) as session:
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} == {
            "powerbi_capabilities",
            "powerbi_auth_status",
            "powerbi_list_workspaces",
            "powerbi_get_workspace",
            "powerbi_list_dashboards",
            "powerbi_get_dashboard",
            "powerbi_list_tiles",
            "powerbi_get_tile",
            "powerbi_dashboard_summary",
            "powerbi_search_dashboards",
            "powerbi_list_reports",
            "powerbi_get_report",
            "powerbi_list_datasets",
            "powerbi_get_dataset",
            "powerbi_list_semantic_models",
            "powerbi_get_semantic_model",
            "powerbi_list_dataset_datasources",
            "powerbi_get_refresh_history",
            "powerbi_xmla_attach",
            "powerbi_xmla_query",
            "powerbi_xmla_execute",
        }

        resources = await session.list_resources()
        assert {str(resource.uri) for resource in resources.resources} == {
            "powerbi://capabilities"
        }

        capabilities = await session.call_tool("powerbi_capabilities", {})
        assert "Power BI MCP Capabilities" in capabilities.structuredContent["content"]

        resource = await session.read_resource("powerbi://capabilities")
        assert "Power BI MCP Capabilities" in resource.contents[0].text

        auth_status = await session.call_tool("powerbi_auth_status", {})
        assert auth_status.structuredContent == AuthStatusResult(
            connected=True,
            account=AccountInfo(preferredUsername="user@example.com"),
            expiresAt=1712345678901,
            knownWorkspaces=["Sales Workspace"],
            resourceStatuses=[
                ResourceScopeStatus(
                    resource="powerbi",
                    connected=True,
                    expiresAt=1712345678901,
                    requiredScopes=[
                        "https://analysis.windows.net/powerbi/api/Dataset.ReadWrite.All"
                    ],
                    grantedScopes=[
                        "Dataset.ReadWrite.All"
                    ],
                ),
                ResourceScopeStatus(
                    resource="fabric",
                    connected=True,
                    expiresAt=1712345678901,
                    requiredScopes=[
                        "https://api.fabric.microsoft.com/Workspace.Read.All",
                        "https://api.fabric.microsoft.com/SemanticModel.Read.All"
                    ],
                    grantedScopes=[
                        "Workspace.Read.All",
                        "SemanticModel.Read.All"
                    ],
                ),
            ],
            localStatusUrl="http://localhost:8787",
            microsoftConnectUrl="http://localhost:8787/auth/microsoft/start",
            microsoftDisconnectUrl="http://localhost:8787/auth/microsoft/disconnect",
        ).model_dump(mode="json", by_alias=True)

        dashboards = await session.call_tool(
            "powerbi_list_dashboards",
            {"workspaceId": "workspace-1"},
        )
        assert dashboards.structuredContent["dashboards"][0]["displayName"] == "Sales Dashboard"
        assert powerbi.last_workspace_id == "workspace-1"

        tiles = await session.call_tool(
            "powerbi_list_tiles",
            {"workspaceId": "workspace-1", "dashboardId": "dashboard-1"},
        )
        assert tiles.structuredContent["tiles"][0]["title"] == "Revenue"

        semantic_models = await session.call_tool(
            "powerbi_list_semantic_models",
            {"workspaceId": "workspace-1"},
        )
        assert semantic_models.structuredContent["semanticModels"][0]["displayName"] == "Sales Model"

        attach = await session.call_tool(
            "powerbi_xmla_attach",
            {"workspaceId": "workspace-1", "semanticModelName": "Sales Model"},
        )
        assert attach.structuredContent["validated"] is True

        query = await session.call_tool(
            "powerbi_xmla_query",
            {
                "workspaceId": "workspace-1",
                "semanticModelName": "Sales Model",
                "query": "EVALUATE ROW(\"Metric\", 1)",
            },
        )
        assert query.structuredContent["rows"][0]["Metric"] == 1

    await http_client.aclose()


def test_server_file_imports_the_way_mcp_cli_imports_it() -> None:
    server_path = Path(__file__).parents[1] / "src" / "powerbi_mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("mcp_cli_server_import_test", server_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.mcp is module.app


def test_can_bind_localhost_detects_busy_port() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    try:
        assert _can_bind_localhost(sock.getsockname()[1]) is False
    finally:
        sock.close()


@pytest.mark.anyio
async def test_mcp_server_stays_up_when_helper_port_is_busy(config_factory) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]

    http_client = httpx.AsyncClient()
    runtime = RuntimeServices(
        config=config_factory(
            port=port,
            localBaseUrl=f"http://localhost:{port}",
        ),
        microsoft_auth=StubAuthService(),
        powerbi=StubPowerBIClient(),
        fabric=StubFabricClient(),
        xmla=StubXMLAClient(),
        http_client=http_client,
        owns_http_client=False,
        start_helper_server=True,
    )
    server = create_mcp_server(runtime)

    try:
        async with create_connected_server_and_client_session(
            server,
            raise_exceptions=True,
        ) as session:
            auth_status = await session.call_tool("powerbi_auth_status", {})
            assert auth_status.structuredContent["connected"] is True
    finally:
        sock.close()
        await http_client.aclose()
