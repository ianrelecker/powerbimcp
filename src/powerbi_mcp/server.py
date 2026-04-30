import contextlib
import socket
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import anyio
import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP

from powerbi_mcp.config import AppConfig, load_config
from powerbi_mcp.helper_app import create_helper_app
from powerbi_mcp.microsoft_auth import MicrosoftAuthService
from powerbi_mcp.models import (
    AuthStatusResult,
    DashboardListResult,
    DashboardResult,
    DashboardSearchResult,
    DashboardSummaryResult,
    DatasourceListResult,
    DatasetListResult,
    DatasetResult,
    PowerBICapabilitiesResult,
    RefreshHistoryResult,
    ReportListResult,
    ReportResult,
    TileListResult,
    TileResult,
    WorkspaceListResult,
    WorkspaceResult,
)
from powerbi_mcp.powerbi_api import PowerBIClient


CAPABILITIES_PATH = Path(__file__).parents[2] / "POWERBI_MCP_CAPABILITIES.md"


@dataclass
class RuntimeServices:
    config: AppConfig
    microsoft_auth: MicrosoftAuthService
    powerbi: PowerBIClient
    http_client: httpx.AsyncClient
    owns_http_client: bool = False
    start_helper_server: bool = True


def create_runtime(
    config: AppConfig | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    start_helper_server: bool = True,
) -> RuntimeServices:
    resolved_config = config or load_config()
    resolved_http_client = http_client or httpx.AsyncClient(
        follow_redirects=False,
        timeout=30.0,
    )
    auth = MicrosoftAuthService(resolved_config, resolved_http_client)
    powerbi = PowerBIClient(auth, resolved_http_client)
    return RuntimeServices(
        config=resolved_config,
        microsoft_auth=auth,
        powerbi=powerbi,
        http_client=resolved_http_client,
        owns_http_client=http_client is None,
        start_helper_server=start_helper_server,
    )


class _RuntimeProvider:
    def __init__(self, factory: Callable[[], RuntimeServices]) -> None:
        self._factory = factory
        self._runtime: RuntimeServices | None = None

    def get(self) -> RuntimeServices:
        if self._runtime is None:
            self._runtime = self._factory()
        return self._runtime

    def reset(self) -> None:
        self._runtime = None


class _HelperServerRunner:
    def __init__(self, runtime: RuntimeServices) -> None:
        self._runtime = runtime
        self._server: uvicorn.Server | None = None

    async def run(self, *, task_status: anyio.abc.TaskStatus[None]) -> None:
        if not _can_bind_localhost(self._runtime.config.port):
            print(
                "Claude Power BI MCP local helper was not started because "
                f"localhost:{self._runtime.config.port} is already in use. "
                "Close the other process using that port, or set PORT and "
                "LOCAL_BASE_URL to a different localhost port that also matches "
                "the Azure redirect URI.",
                file=sys.stderr,
            )
            task_status.started()
            return

        app = create_helper_app(self._runtime.config, self._runtime.microsoft_auth)
        config = uvicorn.Config(
            app,
            host="localhost",
            port=self._runtime.config.port,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        self._server = server

        async def wait_until_started() -> None:
            with anyio.fail_after(5):
                while not server.started and not server.should_exit:
                    await anyio.sleep(0.05)

            if not server.started:
                raise RuntimeError(
                    f"Failed to start local helper server on port {self._runtime.config.port}"
                )

            print(
                f"Claude Power BI MCP local helper listening on port {self._runtime.config.port}",
                file=sys.stderr,
            )
            print(
                f"Local helper URL: {self._runtime.config.localBaseUrl}",
                file=sys.stderr,
            )
            print(
                f"Microsoft callback URI: {self._runtime.config.entra.redirectUri}",
                file=sys.stderr,
            )
            task_status.started()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(wait_until_started)
            try:
                await server.serve()
            finally:
                task_group.cancel_scope.cancel()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True


def _can_bind_localhost(port: int) -> bool:
    addresses: list[tuple[int, tuple[str, int] | tuple[str, int, int, int]]] = [
        (socket.AF_INET, ("127.0.0.1", port)),
    ]
    if socket.has_ipv6:
        addresses.append((socket.AF_INET6, ("::1", port, 0, 0)))

    for family, address in addresses:
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.bind(address)
        except OSError:
            return False
        finally:
            sock.close()

    return True


def _load_capabilities_text() -> str:
    return CAPABILITIES_PATH.read_text("utf-8")


def _create_server(runtime_provider: _RuntimeProvider) -> FastMCP:
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastMCP) -> Iterator[dict[str, object]]:
        runtime = runtime_provider.get()
        helper_runner = (
            _HelperServerRunner(runtime) if runtime.start_helper_server else None
        )

        async with anyio.create_task_group() as task_group:
            if helper_runner is not None:
                await task_group.start(helper_runner.run)
            try:
                yield {"config": runtime.config}
            finally:
                if helper_runner is not None:
                    await helper_runner.stop()
                if runtime.owns_http_client:
                    await runtime.http_client.aclose()
                runtime_provider.reset()

    mcp = FastMCP("claude-powerbi-mcp", lifespan=lifespan)

    @mcp.resource(
        "powerbi://capabilities",
        name="powerbi_capabilities",
        title="Power BI MCP Capabilities",
        description="Model-facing guide for using the Power BI MCP server safely and effectively.",
        mime_type="text/markdown",
    )
    def powerbi_capabilities_resource() -> str:
        return _load_capabilities_text()

    @mcp.tool(
        name="powerbi_capabilities",
        description=(
            "Read the model-facing guide for what this Power BI MCP server can do "
            "and how to use workspace, dashboard, tile, report, dataset, and refresh tools."
        ),
    )
    async def powerbi_capabilities() -> PowerBICapabilitiesResult:
        return PowerBICapabilitiesResult(content=_load_capabilities_text())

    @mcp.tool(
        name="powerbi_auth_status",
        description=(
            "Check whether the server is connected to Microsoft for Power BI "
            "and see configured workspace hints and required scopes."
        ),
    )
    async def powerbi_auth_status() -> AuthStatusResult:
        runtime = runtime_provider.get()
        status = await runtime.microsoft_auth.get_status()
        return AuthStatusResult(
            connected=status.connected,
            account=status.account,
            expiresAt=status.expiresAt,
            knownWorkspaces=status.knownWorkspaces,
            requiredScopes=status.requiredScopes,
            grantedScopes=status.grantedScopes,
            missingScopes=status.missingScopes,
            localStatusUrl=runtime.config.localBaseUrl,
            microsoftConnectUrl=urljoin(
                runtime.config.localBaseUrl, "/auth/microsoft/start"
            ),
            microsoftDisconnectUrl=urljoin(
                runtime.config.localBaseUrl, "/auth/microsoft/disconnect"
            ),
        )

    @mcp.tool(
        name="powerbi_list_workspaces",
        description=(
            "List Power BI workspaces the signed-in user can access. "
            "Use nameContains to narrow the results client-side."
        ),
    )
    async def powerbi_list_workspaces(
        top: int = 100,
        skip: int = 0,
        nameContains: str | None = None,
    ) -> WorkspaceListResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.list_workspaces(
            top=top,
            skip=skip,
            nameContains=nameContains,
        )

    @mcp.tool(
        name="powerbi_get_workspace",
        description="Get one Power BI workspace by workspace ID.",
    )
    async def powerbi_get_workspace(workspaceId: str) -> WorkspaceResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.get_workspace(workspaceId=workspaceId)

    @mcp.tool(
        name="powerbi_list_dashboards",
        description=(
            "List dashboards in My workspace, or in a specified workspace when "
            "workspaceId is provided."
        ),
    )
    async def powerbi_list_dashboards(
        workspaceId: str | None = None,
    ) -> DashboardListResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.list_dashboards(workspaceId=workspaceId)

    @mcp.tool(
        name="powerbi_get_dashboard",
        description="Get one dashboard by ID from My workspace or a specified workspace.",
    )
    async def powerbi_get_dashboard(
        dashboardId: str,
        workspaceId: str | None = None,
    ) -> DashboardResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.get_dashboard(
            workspaceId=workspaceId,
            dashboardId=dashboardId,
        )

    @mcp.tool(
        name="powerbi_list_tiles",
        description="List tiles for a dashboard from My workspace or a specified workspace.",
    )
    async def powerbi_list_tiles(
        dashboardId: str,
        workspaceId: str | None = None,
    ) -> TileListResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.list_tiles(
            workspaceId=workspaceId,
            dashboardId=dashboardId,
        )

    @mcp.tool(
        name="powerbi_get_tile",
        description="Get one tile by dashboard ID and tile ID.",
    )
    async def powerbi_get_tile(
        dashboardId: str,
        tileId: str,
        workspaceId: str | None = None,
    ) -> TileResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.get_tile(
            workspaceId=workspaceId,
            dashboardId=dashboardId,
            tileId=tileId,
        )

    @mcp.tool(
        name="powerbi_dashboard_summary",
        description=(
            "Get a dashboard plus its tiles and related reports/datasets where "
            "those relationships are exposed by the Power BI REST API."
        ),
    )
    async def powerbi_dashboard_summary(
        dashboardId: str,
        workspaceId: str | None = None,
    ) -> DashboardSummaryResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.dashboard_summary(
            workspaceId=workspaceId,
            dashboardId=dashboardId,
        )

    @mcp.tool(
        name="powerbi_search_dashboards",
        description=(
            "Search dashboard display names in one workspace, or across the first "
            "maxWorkspaces accessible workspaces."
        ),
    )
    async def powerbi_search_dashboards(
        query: str,
        workspaceId: str | None = None,
        maxWorkspaces: int = 25,
    ) -> DashboardSearchResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.search_dashboards(
            query=query,
            workspaceId=workspaceId,
            maxWorkspaces=maxWorkspaces,
        )

    @mcp.tool(
        name="powerbi_list_reports",
        description="List reports in My workspace or a specified workspace.",
    )
    async def powerbi_list_reports(
        workspaceId: str | None = None,
    ) -> ReportListResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.list_reports(workspaceId=workspaceId)

    @mcp.tool(
        name="powerbi_get_report",
        description="Get one report by ID from My workspace or a specified workspace.",
    )
    async def powerbi_get_report(
        reportId: str,
        workspaceId: str | None = None,
    ) -> ReportResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.get_report(
            workspaceId=workspaceId,
            reportId=reportId,
        )

    @mcp.tool(
        name="powerbi_list_datasets",
        description="List datasets in My workspace or a specified workspace.",
    )
    async def powerbi_list_datasets(
        workspaceId: str | None = None,
    ) -> DatasetListResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.list_datasets(workspaceId=workspaceId)

    @mcp.tool(
        name="powerbi_get_dataset",
        description="Get one dataset by ID from My workspace or a specified workspace.",
    )
    async def powerbi_get_dataset(
        datasetId: str,
        workspaceId: str | None = None,
    ) -> DatasetResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.get_dataset(
            workspaceId=workspaceId,
            datasetId=datasetId,
        )

    @mcp.tool(
        name="powerbi_list_dataset_datasources",
        description="List data sources configured for a dataset.",
    )
    async def powerbi_list_dataset_datasources(
        datasetId: str,
        workspaceId: str | None = None,
    ) -> DatasourceListResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.list_dataset_datasources(
            workspaceId=workspaceId,
            datasetId=datasetId,
        )

    @mcp.tool(
        name="powerbi_get_refresh_history",
        description="Get recent refresh history for a dataset.",
    )
    async def powerbi_get_refresh_history(
        datasetId: str,
        workspaceId: str | None = None,
        top: int = 10,
    ) -> RefreshHistoryResult:
        runtime = runtime_provider.get()
        return await runtime.powerbi.get_refresh_history(
            workspaceId=workspaceId,
            datasetId=datasetId,
            top=top,
        )

    return mcp


def create_mcp_server(runtime: RuntimeServices) -> FastMCP:
    return _create_server(_RuntimeProvider(lambda: runtime))


def create_default_server() -> FastMCP:
    return _create_server(_RuntimeProvider(create_runtime))


mcp = create_default_server()
app = mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
