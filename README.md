# Power BI MCP

This lets Claude Desktop inspect Power BI workspaces, dashboards, tiles, reports, datasets, data sources, and refresh history through the Power BI REST API.

It is a local MCP server. Claude starts it on your computer when Claude Desktop opens, and the helper web page only handles local Microsoft sign-in.

## What Claude Can Do

Claude can:

- List Power BI workspaces the signed-in user can access.
- List and search dashboards in My workspace or shared workspaces.
- Read dashboard metadata, embed/web URLs, and tile metadata.
- Summarize a dashboard by combining its dashboard details, tiles, related reports, and related datasets.
- List reports and datasets in a workspace.
- Inspect dataset data sources and recent refresh history.

Claude can also read [POWERBI_MCP_CAPABILITIES.md](POWERBI_MCP_CAPABILITIES.md) through the `powerbi_capabilities` tool or the `powerbi://capabilities` MCP resource.

This uses the Power BI REST API at `https://api.powerbi.com/v1.0/myorg`; it does not call Microsoft Graph APIs.

## Setup Checklist

You need four things:

- `uv` installed on the computer running Claude Desktop.
- A Microsoft Entra app registration with Power BI Service delegated permissions.
- A local `.env` file with your app values.
- A Claude Desktop config entry for this MCP server.

## 1. Install uv

`uv` is the Python runner Claude will use to start this MCP server.

macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen your terminal, then check that it installed:

```bash
uv --version
```

## 2. Create The Microsoft App

In the Azure Portal, create a Microsoft Entra app registration for local use.

Use these settings:

- Platform: `Web`
- Redirect URI: `http://localhost:8787/auth/microsoft/callback`
- Supported account type: `Accounts in this organizational directory only`
- Advanced setting: `Allow public client flows = No`

Create a client secret under `Certificates & secrets`. Copy the secret `Value`, not the `Secret ID`.

Add these delegated API permissions under **Power BI Service**:

- `Workspace.Read.All`
- `Dashboard.Read.All`
- `Report.Read.All`
- `Dataset.Read.All`

The OAuth sign-in request also includes these standard OpenID Connect scopes so the helper can identify the signed-in user and keep a refresh token:

- `openid`
- `profile`
- `email`
- `offline_access`

If your organization requires admin approval, click `Grant admin consent`.

## 3. Create Your .env File

Copy `.env.example` to `.env`, then fill in the values.

Important fields:

- `POWERBI_TENANT_ID`: the Azure tenant/directory ID.
- `POWERBI_CLIENT_ID`: the Azure app/client ID.
- `POWERBI_CLIENT_SECRET`: the client secret `Value`.
- `TOKEN_ENCRYPTION_KEY`: a base64 32-byte key used to encrypt the local token cache.
- `KNOWN_WORKSPACES`: optional comma-separated workspace IDs or names to show as hints.

Generate `TOKEN_ENCRYPTION_KEY` with:

```bash
python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

The default OAuth scopes request read-only Power BI REST access:

```text
openid profile email offline_access
https://analysis.windows.net/powerbi/api/Workspace.Read.All
https://analysis.windows.net/powerbi/api/Dashboard.Read.All
https://analysis.windows.net/powerbi/api/Report.Read.All
https://analysis.windows.net/powerbi/api/Dataset.Read.All
```

## 4. Add It To Claude Desktop

Use [claude_desktop_config.json](claude_desktop_config.json) as the starting point. It keeps Claude's default `preferences` block and adds the `powerbi` MCP server.

Replace this example path:

```text
C:\Users\YOUR_WINDOWS_USER\Documents\powerbimcp
```

with the real full path to this repo on your computer.

Keep Microsoft secrets in `.env`. Do not paste tenant IDs, client secrets, or token keys directly into Claude's config.

After saving the config, fully quit and reopen Claude Desktop.

## 5. Connect Power BI

Do not run the MCP server manually for normal use. Let Claude Desktop start it.

After Claude Desktop reopens, the local auth site should be available here:

```text
http://localhost:8787/
```

If that page is not available yet, open a Claude chat and ask:

```text
Check my Power BI auth status with the powerbi MCP server.
```

Claude should start the MCP server and call `powerbi_auth_status`. The result includes the Microsoft connect URL.

To sign in directly, open:

```text
http://localhost:8787/auth/microsoft/start
```

Sign in with the Microsoft account Claude should use for Power BI. Tokens are stored locally at `.tokens/powerbi-token.json`, encrypted with `TOKEN_ENCRYPTION_KEY`.

## Everyday Use

Once authenticated, ask Claude things like:

- `List my Power BI workspaces.`
- `Find dashboards with sales in the name.`
- `Summarize the Sales dashboard in this workspace.`
- `List the tiles on this dashboard.`
- `Show reports and datasets in this workspace.`
- `Check the refresh history for this dataset.`

For shared workspaces, mention the workspace name or ID in your request.

## Troubleshooting

If Claude shows `Server disconnected`, click `View Logs`.

Common fixes:

- If the logs say `TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key`, regenerate `TOKEN_ENCRYPTION_KEY` and update `.env`.
- If the MCP details still show placeholder values like `POWERBI_TENANT_ID=your-tenant-id`, remove any old environment-variable block from Claude's config and use `--env-file .env`.
- If the logs say the port is already in use, something else is using port `8787`. Stop the other process, or change `PORT` and `LOCAL_BASE_URL`, then update the Azure redirect URI to match.
- If Microsoft sign-in fails, confirm the Azure redirect URI exactly matches `http://localhost:8787/auth/microsoft/callback`.
- If `powerbi_auth_status` reports `missingScopes`, add the missing Power BI Service permissions in Azure, grant consent if needed, then reconnect.

## API References

- [Power BI dashboards REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/dashboards)
- [Power BI groups/workspaces REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/groups)
- [Power BI reports REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/reports)
- [Power BI datasets REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets)
