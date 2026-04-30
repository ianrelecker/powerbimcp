from __future__ import annotations

import httpx
import pytest

from powerbi_mcp.powerbi_api import PowerBIClient


class StaticAuthService:
    async def get_access_token(self) -> str:
        return "access-token"


@pytest.mark.anyio
async def test_list_workspaces_and_dashboards() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer access-token"

        if request.url.path.endswith("/groups"):
            assert request.url.params["$top"] == "100"
            assert request.url.params["$skip"] == "0"
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "workspace-1",
                            "name": "Sales Workspace",
                            "type": "Workspace",
                            "isReadOnly": False,
                        },
                        {
                            "id": "workspace-2",
                            "name": "Finance Workspace",
                            "type": "Workspace",
                            "isReadOnly": True,
                        },
                    ]
                },
            )

        if request.url.path.endswith("/groups/workspace-1/dashboards"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "dashboard-1",
                            "displayName": "Sales Dashboard",
                            "webUrl": "https://app.powerbi.com/groups/workspace-1/dashboards/dashboard-1",
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    powerbi = PowerBIClient(StaticAuthService(), client)

    workspaces = await powerbi.list_workspaces(nameContains="sales")
    assert len(workspaces.workspaces) == 1
    assert workspaces.workspaces[0].name == "Sales Workspace"

    dashboards = await powerbi.list_dashboards(workspaceId="workspace-1")
    assert dashboards.workspaceId == "workspace-1"
    assert dashboards.dashboards[0].displayName == "Sales Dashboard"

    await client.aclose()


@pytest.mark.anyio
async def test_dashboard_summary_collects_tiles_reports_and_datasets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/groups/workspace-1/dashboards/dashboard-1"):
            return httpx.Response(
                200,
                json={"id": "dashboard-1", "displayName": "Executive Sales"},
            )

        if request.url.path.endswith("/groups/workspace-1/dashboards/dashboard-1/tiles"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "tile-1",
                            "title": "Revenue",
                            "reportId": "report-1",
                            "datasetId": "dataset-1",
                        }
                    ]
                },
            )

        if request.url.path.endswith("/groups/workspace-1/reports/report-1"):
            return httpx.Response(
                200,
                json={
                    "id": "report-1",
                    "name": "Sales Report",
                    "datasetId": "dataset-1",
                },
            )

        if request.url.path.endswith("/groups/workspace-1/datasets/dataset-1"):
            return httpx.Response(
                200,
                json={
                    "id": "dataset-1",
                    "name": "Sales Dataset",
                    "isRefreshable": True,
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    powerbi = PowerBIClient(StaticAuthService(), client)

    summary = await powerbi.dashboard_summary(
        workspaceId="workspace-1",
        dashboardId="dashboard-1",
    )

    assert summary.dashboard.displayName == "Executive Sales"
    assert summary.tiles[0].title == "Revenue"
    assert summary.reports[0].name == "Sales Report"
    assert summary.datasets[0].name == "Sales Dataset"
    assert summary.warnings == []

    await client.aclose()


@pytest.mark.anyio
async def test_dataset_datasources_and_refresh_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/groups/workspace-1/datasets/dataset-1/datasources"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "datasourceId": "source-1",
                            "datasourceType": "Sql",
                            "connectionDetails": {
                                "server": "sql.example.com",
                                "database": "Sales",
                            },
                        }
                    ]
                },
            )

        if request.url.path.endswith("/groups/workspace-1/datasets/dataset-1/refreshes"):
            assert request.url.params["$top"] == "5"
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "requestId": "request-1",
                            "refreshType": "ViaApi",
                            "status": "Completed",
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    powerbi = PowerBIClient(StaticAuthService(), client)

    datasources = await powerbi.list_dataset_datasources(
        workspaceId="workspace-1",
        datasetId="dataset-1",
    )
    assert datasources.datasources[0].connectionDetails["database"] == "Sales"

    refreshes = await powerbi.get_refresh_history(
        workspaceId="workspace-1",
        datasetId="dataset-1",
        top=5,
    )
    assert refreshes.refreshes[0].status == "Completed"

    await client.aclose()
