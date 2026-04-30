from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx

from .microsoft_auth import MicrosoftAuthService
from .models import (
    DashboardInfo,
    DashboardListResult,
    DashboardResult,
    DashboardSearchMatch,
    DashboardSearchResult,
    DashboardSummaryResult,
    DatasetInfo,
    DatasetListResult,
    DatasetResult,
    DatasourceInfo,
    DatasourceListResult,
    RefreshHistoryResult,
    RefreshInfo,
    ReportInfo,
    ReportListResult,
    ReportResult,
    TileInfo,
    TileListResult,
    TileResult,
    WorkspaceInfo,
    WorkspaceListResult,
    WorkspaceResult,
)


POWERBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"


class PowerBIClient:
    def __init__(
        self,
        auth_service: MicrosoftAuthService,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth_service = auth_service
        self._http_client = http_client

    @asynccontextmanager
    async def _client(self) -> Any:
        if self._http_client is not None:
            yield self._http_client
            return

        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
            yield client

    async def list_workspaces(
        self,
        *,
        top: int = 100,
        skip: int = 0,
        nameContains: str | None = None,
    ) -> WorkspaceListResult:
        capped_top = min(max(top, 1), 5000)
        params = httpx.QueryParams({"$top": str(capped_top), "$skip": str(max(skip, 0))})
        result = await self._request(f"/groups?{params}")
        workspaces = [self._map_workspace(item) for item in result.get("value", [])]
        if nameContains:
            needle = nameContains.casefold()
            workspaces = [
                workspace
                for workspace in workspaces
                if needle in workspace.name.casefold()
            ]

        return WorkspaceListResult(
            workspaces=workspaces,
            top=capped_top,
            skip=max(skip, 0),
            nameContains=nameContains,
        )

    async def get_workspace(self, *, workspaceId: str) -> WorkspaceResult:
        result = await self._request(f"/groups/{self._segment(workspaceId)}")
        return WorkspaceResult(workspace=self._map_workspace(result))

    async def list_dashboards(
        self,
        *,
        workspaceId: str | None = None,
    ) -> DashboardListResult:
        result = await self._request(
            self._workspace_path(workspaceId, "dashboards")
        )
        return DashboardListResult(
            workspaceId=workspaceId,
            dashboards=[self._map_dashboard(item) for item in result.get("value", [])],
        )

    async def get_dashboard(
        self,
        *,
        dashboardId: str,
        workspaceId: str | None = None,
    ) -> DashboardResult:
        result = await self._request(
            self._workspace_path(workspaceId, f"dashboards/{self._segment(dashboardId)}")
        )
        return DashboardResult(
            workspaceId=workspaceId,
            dashboard=self._map_dashboard(result),
        )

    async def list_tiles(
        self,
        *,
        dashboardId: str,
        workspaceId: str | None = None,
    ) -> TileListResult:
        result = await self._request(
            self._workspace_path(
                workspaceId,
                f"dashboards/{self._segment(dashboardId)}/tiles",
            )
        )
        return TileListResult(
            workspaceId=workspaceId,
            dashboardId=dashboardId,
            tiles=[self._map_tile(item) for item in result.get("value", [])],
        )

    async def get_tile(
        self,
        *,
        dashboardId: str,
        tileId: str,
        workspaceId: str | None = None,
    ) -> TileResult:
        result = await self._request(
            self._workspace_path(
                workspaceId,
                f"dashboards/{self._segment(dashboardId)}/tiles/{self._segment(tileId)}",
            )
        )
        return TileResult(
            workspaceId=workspaceId,
            dashboardId=dashboardId,
            tile=self._map_tile(result),
        )

    async def list_reports(
        self,
        *,
        workspaceId: str | None = None,
    ) -> ReportListResult:
        result = await self._request(self._workspace_path(workspaceId, "reports"))
        return ReportListResult(
            workspaceId=workspaceId,
            reports=[self._map_report(item) for item in result.get("value", [])],
        )

    async def get_report(
        self,
        *,
        reportId: str,
        workspaceId: str | None = None,
    ) -> ReportResult:
        result = await self._request(
            self._workspace_path(workspaceId, f"reports/{self._segment(reportId)}")
        )
        return ReportResult(workspaceId=workspaceId, report=self._map_report(result))

    async def list_datasets(
        self,
        *,
        workspaceId: str | None = None,
    ) -> DatasetListResult:
        result = await self._request(self._workspace_path(workspaceId, "datasets"))
        return DatasetListResult(
            workspaceId=workspaceId,
            datasets=[self._map_dataset(item) for item in result.get("value", [])],
        )

    async def get_dataset(
        self,
        *,
        datasetId: str,
        workspaceId: str | None = None,
    ) -> DatasetResult:
        result = await self._request(
            self._workspace_path(workspaceId, f"datasets/{self._segment(datasetId)}")
        )
        return DatasetResult(workspaceId=workspaceId, dataset=self._map_dataset(result))

    async def list_dataset_datasources(
        self,
        *,
        datasetId: str,
        workspaceId: str | None = None,
    ) -> DatasourceListResult:
        result = await self._request(
            self._workspace_path(
                workspaceId,
                f"datasets/{self._segment(datasetId)}/datasources",
            )
        )
        return DatasourceListResult(
            workspaceId=workspaceId,
            datasetId=datasetId,
            datasources=[
                self._map_datasource(item) for item in result.get("value", [])
            ],
        )

    async def get_refresh_history(
        self,
        *,
        datasetId: str,
        workspaceId: str | None = None,
        top: int = 10,
    ) -> RefreshHistoryResult:
        params = httpx.QueryParams({"$top": str(min(max(top, 1), 60))})
        result = await self._request(
            self._workspace_path(
                workspaceId,
                f"datasets/{self._segment(datasetId)}/refreshes",
            )
            + f"?{params}"
        )
        return RefreshHistoryResult(
            workspaceId=workspaceId,
            datasetId=datasetId,
            refreshes=[
                self._map_refresh(item) for item in result.get("value", [])
            ],
        )

    async def dashboard_summary(
        self,
        *,
        dashboardId: str,
        workspaceId: str | None = None,
    ) -> DashboardSummaryResult:
        dashboard = await self.get_dashboard(
            workspaceId=workspaceId,
            dashboardId=dashboardId,
        )
        tiles = await self.list_tiles(workspaceId=workspaceId, dashboardId=dashboardId)

        reports: list[ReportInfo] = []
        datasets: list[DatasetInfo] = []
        warnings: list[str] = []
        report_ids = sorted({tile.reportId for tile in tiles.tiles if tile.reportId})
        dataset_ids = sorted({tile.datasetId for tile in tiles.tiles if tile.datasetId})

        for report_id in report_ids:
            try:
                report = await self.get_report(
                    workspaceId=workspaceId,
                    reportId=report_id,
                )
                reports.append(report.report)
                if report.report.datasetId:
                    dataset_ids.append(report.report.datasetId)
            except Exception as error:
                warnings.append(f"Could not load report {report_id}: {error}")

        for dataset_id in sorted(set(dataset_ids)):
            try:
                dataset = await self.get_dataset(
                    workspaceId=workspaceId,
                    datasetId=dataset_id,
                )
                datasets.append(dataset.dataset)
            except Exception as error:
                warnings.append(f"Could not load dataset {dataset_id}: {error}")

        return DashboardSummaryResult(
            workspaceId=workspaceId,
            dashboard=dashboard.dashboard,
            tiles=tiles.tiles,
            reports=reports,
            datasets=datasets,
            warnings=warnings,
        )

    async def search_dashboards(
        self,
        *,
        query: str,
        workspaceId: str | None = None,
        maxWorkspaces: int = 25,
    ) -> DashboardSearchResult:
        needle = query.casefold()
        warnings: list[str] = []
        matches: list[DashboardSearchMatch] = []

        if workspaceId:
            dashboards = await self.list_dashboards(workspaceId=workspaceId)
            matches = [
                DashboardSearchMatch(workspace=None, dashboard=dashboard)
                for dashboard in dashboards.dashboards
                if needle in dashboard.displayName.casefold()
            ]
            return DashboardSearchResult(
                query=query,
                workspaceId=workspaceId,
                searchedWorkspaceCount=1,
                matches=matches,
                warnings=warnings,
            )

        workspaces = await self.list_workspaces(top=maxWorkspaces)
        for workspace in workspaces.workspaces:
            try:
                dashboards = await self.list_dashboards(workspaceId=workspace.id)
            except Exception as error:
                warnings.append(f"Could not search workspace {workspace.name}: {error}")
                continue

            matches.extend(
                DashboardSearchMatch(workspace=workspace, dashboard=dashboard)
                for dashboard in dashboards.dashboards
                if needle in dashboard.displayName.casefold()
            )

        return DashboardSearchResult(
            query=query,
            workspaceId=None,
            searchedWorkspaceCount=len(workspaces.workspaces),
            matches=matches,
            warnings=warnings,
        )

    async def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._auth_service.get_access_token()
        url = self._url(path)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        async with self._client() as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=json_body,
            )

        if not response.is_success:
            raise RuntimeError(self._format_error(response, method, path))

        if response.status_code == 204 or not response.content:
            return {}

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(
                f"Power BI API returned an unexpected response for {method} {path}"
            )
        return data

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return POWERBI_API_BASE + (path if path.startswith("/") else f"/{path}")

    def _workspace_path(self, workspace_id: str | None, suffix: str) -> str:
        normalized_suffix = suffix.strip("/")
        if workspace_id:
            return f"/groups/{self._segment(workspace_id)}/{normalized_suffix}"
        return f"/{normalized_suffix}"

    def _segment(self, value: str) -> str:
        return quote(value, safe="")

    def _format_error(self, response: httpx.Response, method: str, path: str) -> str:
        detail = response.text
        try:
            body = response.json()
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict):
                    detail = str(
                        error.get("message") or error.get("code") or response.text
                    )
                elif isinstance(error, str):
                    detail = error
        except Exception:
            pass

        return (
            f"Power BI API request failed ({method} {path}): "
            f"{response.status_code} {response.reason_phrase}: {detail}"
        )

    def _map_workspace(self, data: dict[str, Any]) -> WorkspaceInfo:
        return WorkspaceInfo.model_validate(data)

    def _map_dashboard(self, data: dict[str, Any]) -> DashboardInfo:
        return DashboardInfo.model_validate(data)

    def _map_tile(self, data: dict[str, Any]) -> TileInfo:
        return TileInfo.model_validate(data)

    def _map_report(self, data: dict[str, Any]) -> ReportInfo:
        return ReportInfo.model_validate(data)

    def _map_dataset(self, data: dict[str, Any]) -> DatasetInfo:
        return DatasetInfo.model_validate(data)

    def _map_datasource(self, data: dict[str, Any]) -> DatasourceInfo:
        return DatasourceInfo.model_validate(data)

    def _map_refresh(self, data: dict[str, Any]) -> RefreshInfo:
        return RefreshInfo.model_validate(data)
