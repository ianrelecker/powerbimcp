# Power BI MCP Capabilities

This MCP server gives Claude local delegated access to Power BI dashboard metadata through the Power BI REST API. Use `powerbi_auth_status` first. If `missingScopes` is not empty, reconnect Microsoft from the local helper URL before using tools that need those scopes.

## Authentication

- The server signs in through Microsoft Entra and stores an encrypted local refresh token.
- Tokens are requested for the Power BI resource, not Microsoft Graph.
- The default scopes are read-only: workspace, dashboard, report, and dataset read access.

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

## Safety Notes

- The server acts as the signed-in user and can access only Power BI content where that user already has permission.
- This server is intentionally read-focused. It does not expose dashboard deletion, tile cloning, dataset refresh triggering, or other write tools.
- Embed URLs and web URLs can reveal tenant-specific content locations. Share them only with users who already have appropriate Power BI access.
