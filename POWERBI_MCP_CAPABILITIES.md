# Power BI MCP Capabilities

This MCP server gives Claude local delegated access to Power BI REST metadata, Fabric semantic model metadata, and Premium XMLA semantic model operations. Use `powerbi_auth_status` first. If `missingScopes` is not empty, reconnect Microsoft from the local helper URL before using tools that need those scopes.

## Authentication

- The server signs in through Microsoft Entra and stores an encrypted local refresh token.
- Tokens are requested per resource: Power BI uses `https://analysis.windows.net/powerbi/api/`, and Fabric uses `https://api.fabric.microsoft.com/`. Microsoft Graph is not used.
- The default Power BI scopes are workspace, dashboard, report, and dataset read/write access. Dataset read/write is required for XMLA write support.
- The default Fabric scopes are read-only: workspace read for semantic model listing and semantic model read for item lookup.
- `powerbi_auth_status` reports Power BI and Fabric resource consent separately in `resourceStatuses`.

## Workspaces

- Use `powerbi_list_workspaces` to discover accessible workspaces.
- Use `powerbi_get_workspace` when you already have a workspace ID.
- Leave `workspaceId` blank for My workspace operations.
- Pass `workspaceId` for shared workspaces. Workspace names can repeat, so prefer IDs after discovery.

## Dashboards And Tiles

- Use `powerbi_list_dashboards` to inspect dashboards in My workspace or a shared workspace.
- Use `powerbi_search_dashboards` when the user gives a dashboard name fragment.
- Use `powerbi_get_dashboard` for one dashboard's metadata and URLs.
- Use `powerbi_list_tiles` or `powerbi_get_tile` for dashboard tile metadata, including related `reportId` and `datasetId` when Power BI exposes them.
- Use `powerbi_dashboard_summary` for the best dashboard overview: dashboard metadata, tiles, related reports, and related datasets.

## Reports

- Use `powerbi_list_reports` to inspect reports in My workspace or a shared workspace.
- Use `powerbi_get_report` for a report's metadata, web URL, embed URL, report type, and dataset link.

## Datasets

- Use `powerbi_list_datasets` and `powerbi_get_dataset` for dataset metadata.
- Use `powerbi_list_dataset_datasources` to see configured data source metadata for a dataset.
- Use `powerbi_get_refresh_history` to inspect recent refresh status, failures, and timestamps.

## Semantic Models

- Use `powerbi_list_semantic_models` to list Fabric semantic models in a workspace.
- Use `powerbi_get_semantic_model` when you already have a workspace ID and semantic model ID.
- Prefer IDs after discovery because display names can repeat or be renamed.

## XMLA

- Use `powerbi_xmla_attach` before XMLA work. Provide `workspaceId` plus either `semanticModelId` or `semanticModelName`.
- Attach builds `powerbi://api.powerbi.com/v1.0/{tenantAlias}/{workspace}` and URI-encodes the workspace reference. The default tenant alias is `myorg`; override it for guest or cross-tenant access.
- Attach validates the catalog through the .NET bridge when `validate=true`. It retries the documented duplicate-name form `name - guid` for workspace and semantic model catalog names.
- Use `powerbi_xmla_query` for DAX, MDX, or DMV read queries. Keep `maxRows` low unless the user explicitly needs more rows.
- Use `powerbi_xmla_execute` only for explicit XMLA/TMSL write commands. It requires `POWERBI_XMLA_ALLOW_WRITES=true` and confirmation text `I_UNDERSTAND_XMLA_WRITES_CAN_CHANGE_SEMANTIC_MODELS`.
- Bridge errors are sanitized so access tokens are not returned to Claude.

## Safety Notes

- The server acts as the signed-in user and can access only Power BI content where that user already has permission.
- Power BI REST tools remain read-focused. This server does not expose dashboard deletion, tile cloning, dataset refresh triggering, or Fabric semantic model create/update APIs.
- XMLA/TMSL writes can change semantic model metadata or processing state. Use them only when the user clearly asks for that operation and the local write opt-in is enabled.
- XMLA read access requires Build permission on the semantic model. XMLA writes require Contributor or higher/workspace-equivalent write permission plus a Premium/PPU/Fabric workspace with XMLA Read Write enabled.
- Embed URLs and web URLs can reveal tenant-specific content locations. Share them only with users who already have appropriate Power BI access.
