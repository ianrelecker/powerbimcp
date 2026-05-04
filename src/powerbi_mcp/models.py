from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AppModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AccountInfo(AppModel):
    name: str | None = None
    preferredUsername: str | None = None
    oid: str | None = None
    tid: str | None = None


class ResourceScopeStatus(AppModel):
    resource: str
    connected: bool
    expiresAt: int | None = None
    requiredScopes: list[str] = Field(default_factory=list)
    grantedScopes: list[str] = Field(default_factory=list)
    missingScopes: list[str] = Field(default_factory=list)


class MicrosoftConnectionStatus(AppModel):
    connected: bool
    account: AccountInfo | None = None
    expiresAt: int | None = None
    knownWorkspaces: list[str]
    requiredScopes: list[str] = Field(default_factory=list)
    grantedScopes: list[str] = Field(default_factory=list)
    missingScopes: list[str] = Field(default_factory=list)
    resourceStatuses: list[ResourceScopeStatus] = Field(default_factory=list)


class AuthStatusResult(MicrosoftConnectionStatus):
    localStatusUrl: str
    microsoftConnectUrl: str
    microsoftDisconnectUrl: str


class PowerBICapabilitiesResult(AppModel):
    content: str


class WorkspaceInfo(AppModel):
    id: str
    name: str
    type: str | None = None
    state: str | None = None
    isReadOnly: bool | None = None
    isOnDedicatedCapacity: bool | None = None
    capacityId: str | None = None
    defaultDatasetStorageFormat: str | None = None


class WorkspaceListResult(AppModel):
    workspaces: list[WorkspaceInfo]
    top: int
    skip: int = 0
    nameContains: str | None = None


class WorkspaceResult(AppModel):
    workspace: WorkspaceInfo


class DashboardInfo(AppModel):
    id: str
    displayName: str
    embedUrl: str | None = None
    webUrl: str | None = None
    isReadOnly: bool | None = None
    appId: str | None = None


class DashboardListResult(AppModel):
    workspaceId: str | None = None
    dashboards: list[DashboardInfo]


class DashboardResult(AppModel):
    workspaceId: str | None = None
    dashboard: DashboardInfo


class TileInfo(AppModel):
    id: str
    title: str | None = None
    embedUrl: str | None = None
    embedData: str | None = None
    rowSpan: int | None = None
    colSpan: int | None = None
    reportId: str | None = None
    datasetId: str | None = None


class TileListResult(AppModel):
    workspaceId: str | None = None
    dashboardId: str
    tiles: list[TileInfo]


class TileResult(AppModel):
    workspaceId: str | None = None
    dashboardId: str
    tile: TileInfo


class ReportInfo(AppModel):
    id: str
    name: str
    datasetId: str | None = None
    webUrl: str | None = None
    embedUrl: str | None = None
    reportType: str | None = None
    isFromPbix: bool | None = None
    isOwnedByMe: bool | None = None
    appId: str | None = None


class ReportListResult(AppModel):
    workspaceId: str | None = None
    reports: list[ReportInfo]


class ReportResult(AppModel):
    workspaceId: str | None = None
    report: ReportInfo


class DatasetInfo(AppModel):
    id: str
    name: str
    configuredBy: str | None = None
    addRowsAPIEnabled: bool | None = None
    isRefreshable: bool | None = None
    isEffectiveIdentityRequired: bool | None = None
    isEffectiveIdentityRolesRequired: bool | None = None
    isOnPremGatewayRequired: bool | None = None
    contentProviderType: str | None = None
    createReportEmbedURL: str | None = None
    qnaEmbedURL: str | None = None
    defaultRetentionPolicy: str | None = None
    targetStorageMode: str | None = None
    endorsementDetails: dict[str, Any] | None = None
    upstreamDataflows: list[dict[str, Any]] = Field(default_factory=list)
    users: list[dict[str, Any]] = Field(default_factory=list)


class DatasetListResult(AppModel):
    workspaceId: str | None = None
    datasets: list[DatasetInfo]


class DatasetResult(AppModel):
    workspaceId: str | None = None
    dataset: DatasetInfo


class SemanticModelInfo(AppModel):
    id: str
    displayName: str
    description: str | None = None
    type: str | None = None
    workspaceId: str
    folderId: str | None = None
    sensitivityLabel: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = Field(default_factory=list)
    defaultIdentity: dict[str, Any] | None = None


class SemanticModelListResult(AppModel):
    workspaceId: str
    semanticModels: list[SemanticModelInfo]
    continuationToken: str | None = None
    continuationUri: str | None = None


class SemanticModelResult(AppModel):
    workspaceId: str
    semanticModel: SemanticModelInfo


class DatasourceInfo(AppModel):
    datasourceId: str | None = None
    gatewayId: str | None = None
    name: str | None = None
    datasourceType: str | None = None
    connectionDetails: dict[str, Any] = Field(default_factory=dict)


class DatasourceListResult(AppModel):
    workspaceId: str | None = None
    datasetId: str
    datasources: list[DatasourceInfo]


class RefreshInfo(AppModel):
    requestId: str | None = None
    id: int | str | None = None
    refreshType: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    status: str | None = None
    serviceExceptionJson: str | None = None
    extendedStatus: str | None = None
    refreshAttempts: list[dict[str, Any]] = Field(default_factory=list)


class RefreshHistoryResult(AppModel):
    workspaceId: str | None = None
    datasetId: str
    refreshes: list[RefreshInfo]


class DashboardSummaryResult(AppModel):
    workspaceId: str | None = None
    dashboard: DashboardInfo
    tiles: list[TileInfo]
    reports: list[ReportInfo] = Field(default_factory=list)
    datasets: list[DatasetInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DashboardSearchMatch(AppModel):
    workspace: WorkspaceInfo | None = None
    dashboard: DashboardInfo


class DashboardSearchResult(AppModel):
    query: str
    workspaceId: str | None = None
    searchedWorkspaceCount: int
    matches: list[DashboardSearchMatch]
    warnings: list[str] = Field(default_factory=list)


class XmlaAttachResult(AppModel):
    workspaceId: str
    workspaceName: str
    semanticModelId: str
    semanticModelName: str
    tenantAlias: str
    serverUrl: str
    initialCatalog: str
    alternateServerUrl: str | None = None
    alternateInitialCatalog: str | None = None
    effectiveServerUrl: str
    effectiveInitialCatalog: str
    validated: bool
    validationError: str | None = None
    writeEnabled: bool
    requirements: list[str]


class XmlaQueryResult(AppModel):
    attach: XmlaAttachResult
    queryType: str
    columns: list[str]
    rows: list[dict[str, Any]]
    rowCount: int
    truncated: bool


class XmlaExecuteResult(AppModel):
    attach: XmlaAttachResult
    commandType: str
    executed: bool
    messages: list[str] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)


class StoredResourceToken(AppModel):
    accessToken: str
    expiresAt: int
    scope: str
    updatedAt: int


class StoredMicrosoftTokens(AppModel):
    refreshToken: str
    accessTokens: dict[str, StoredResourceToken] = Field(default_factory=dict)
    idToken: str | None = None
    account: AccountInfo | None = None
    updatedAt: int
    accessToken: str | None = None
    expiresAt: int | None = None
    scope: str | None = None


class EncryptedPayload(AppModel):
    iv: str
    tag: str
    ciphertext: str
