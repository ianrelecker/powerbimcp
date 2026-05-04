# Power BI MCP

This lets Claude Desktop inspect Power BI workspaces, dashboards, tiles, reports, datasets, data sources, refresh history, Fabric semantic models, and Premium XMLA endpoints.

It is a local MCP server. Claude starts it on your computer when Claude Desktop opens, and the helper web page only handles local Microsoft sign-in.

## What Claude Can Do

Claude can:

- List Power BI workspaces the signed-in user can access.
- List and search dashboards in My workspace or shared workspaces.
- Read dashboard metadata, embed/web URLs, and tile metadata.
- Summarize a dashboard by combining its dashboard details, tiles, related reports, and related datasets.
- List reports, datasets, and Fabric semantic models in a workspace.
- Inspect dataset data sources and recent refresh history.
- Attach to a Premium/PPU/Fabric semantic model through the XMLA endpoint.
- Run DAX, MDX, or DMV read queries through XMLA with row truncation.
- Execute explicit XMLA/TMSL write commands only when local write opt-in and per-call confirmation are both present.

Claude can also read [POWERBI_MCP_CAPABILITIES.md](POWERBI_MCP_CAPABILITIES.md) through the `powerbi_capabilities` tool or the `powerbi://capabilities` MCP resource.

This uses the Power BI REST API at `https://api.powerbi.com/v1.0/myorg`, the Fabric REST API at `https://api.fabric.microsoft.com/v1`, and Power BI Premium XMLA endpoints. It does not call Microsoft Graph APIs.

## Setup Checklist

You need five things:

- `uv` installed on the computer running Claude Desktop.
- A Microsoft Entra app registration with Power BI Service and Microsoft Fabric delegated permissions.
- A local `.env` file with your app values.
- The .NET SDK/runtime for XMLA bridge operations.
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
- `Dataset.ReadWrite.All`

Add these delegated API permissions under **Microsoft Fabric**:

- `Workspace.Read.All`
- `SemanticModel.Read.All`

The OAuth sign-in request also includes these standard OpenID Connect scopes so the helper can identify the signed-in user and keep a refresh token:

- `openid`
- `profile`
- `email`
- `offline_access`

If your organization requires admin approval, click `Grant admin consent`.

## 3. Install .NET For XMLA

The MCP host is Python, but XMLA uses a small .NET bridge built with Microsoft's Analysis Services client libraries.

Install the .NET SDK so the default bridge project can run:

```bash
dotnet --version
```

The bundled bridge uses these NuGet packages:

- `Microsoft.AnalysisServices`
- `Microsoft.AnalysisServices.AdomdClient`

For faster startup, you can publish the bridge and set `XMLA_BRIDGE_PATH` to the produced `.dll`:

```bash
dotnet publish xmla_bridge/PowerBIXmlaBridge/PowerBIXmlaBridge.csproj -c Release
```

## 4. Create Your .env File

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

The default OAuth scopes request OpenID, Power BI, and Fabric tokens. Power BI keeps the existing REST read scopes and uses `Dataset.ReadWrite.All` so the same Power BI token can be used for XMLA writes when you explicitly enable them. Fabric is requested as a separate token audience:

```text
openid profile email offline_access
https://analysis.windows.net/powerbi/api/Workspace.Read.All
https://analysis.windows.net/powerbi/api/Dashboard.Read.All
https://analysis.windows.net/powerbi/api/Report.Read.All
https://analysis.windows.net/powerbi/api/Dataset.ReadWrite.All
https://api.fabric.microsoft.com/Workspace.Read.All
https://api.fabric.microsoft.com/SemanticModel.Read.All
```

XMLA defaults are safe for reads:

```text
XMLA_BRIDGE_PATH=xmla_bridge/PowerBIXmlaBridge/PowerBIXmlaBridge.csproj
POWERBI_XMLA_TENANT_ALIAS=myorg
POWERBI_XMLA_ALLOW_WRITES=false
XMLA_BRIDGE_TIMEOUT_SECONDS=60
```

Set `POWERBI_XMLA_ALLOW_WRITES=true` only when you want Claude to be allowed to run XMLA/TMSL write commands. Each write call must also include this exact confirmation text:

```text
I_UNDERSTAND_XMLA_WRITES_CAN_CHANGE_SEMANTIC_MODELS
```

## 5. Add It To Claude Desktop

Use [claude_desktop_config.json](claude_desktop_config.json) as the starting point. It keeps Claude's default `preferences` block and adds the `powerbi` MCP server.

Replace this example path:

```text
C:\Users\YOUR_WINDOWS_USER\Documents\powerbimcp
```

with the real full path to this repo on your computer.

Keep Microsoft secrets in `.env`. Do not paste tenant IDs, client secrets, or token keys directly into Claude's config.

After saving the config, fully quit and reopen Claude Desktop.

## 6. Connect Power BI And Fabric

Do not run the MCP server manually for normal use. Let Claude Desktop start it.

After Claude Desktop reopens, the local auth site should be available here:

```text
http://localhost:8787/
```

If that page is not available yet, open a Claude chat and ask:

```text
Check my Power BI auth status with the powerbi MCP server.
```

Claude should start the MCP server and call `powerbi_auth_status`. The result includes the Microsoft connect URL plus separate Power BI and Fabric resource consent status.

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
- `List semantic models in this workspace.`
- `Attach to the Sales Model semantic model through XMLA.`
- `Run this DAX query against the Sales Model semantic model.`

For shared workspaces, mention the workspace name or ID in your request.

XMLA attach builds this server URL shape:

```text
powerbi://api.powerbi.com/v1.0/{tenantAlias}/{URI-encoded workspace name}
```

If Power BI reports duplicate workspace or semantic model names, retry with IDs or the documented `name - guid` catalog form. The XMLA attach tool returns both the initial candidate and the effective server/catalog validated by the bridge.

## Troubleshooting

If Claude shows `Server disconnected`, click `View Logs`.

Common fixes:

- If the logs say `TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key`, regenerate `TOKEN_ENCRYPTION_KEY` and update `.env`.
- If the MCP details still show placeholder values like `POWERBI_TENANT_ID=your-tenant-id`, remove any old environment-variable block from Claude's config and use `--env-file .env`.
- If the logs say the port is already in use, something else is using port `8787`. Stop the other process, or change `PORT` and `LOCAL_BASE_URL`, then update the Azure redirect URI to match.
- If Microsoft sign-in fails, confirm the Azure redirect URI exactly matches `http://localhost:8787/auth/microsoft/callback`.
- If `powerbi_auth_status` reports `missingScopes`, add the missing Power BI Service or Microsoft Fabric permissions in Azure, grant consent if needed, then reconnect.
- If Fabric semantic model calls fail with authorization errors, confirm the app has Microsoft Fabric delegated `Workspace.Read.All` and `SemanticModel.Read.All` permissions, not just Power BI Service permissions with the same names.
- If XMLA attach fails, confirm the workspace is on Premium, PPU, or Fabric capacity, tenant XMLA settings allow the account, and the account has Build permission on the semantic model.
- If XMLA writes fail, confirm the capacity XMLA endpoint is set to Read Write, the account has Contributor or higher permissions, `POWERBI_XMLA_ALLOW_WRITES=true`, and the write call includes the exact confirmation text.
- If bridge startup fails, run `dotnet --version` and verify `XMLA_BRIDGE_PATH` points to the bundled `.csproj`, a published `.dll`, or an executable bridge.

## API References

- [Power BI dashboards REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/dashboards)
- [Power BI groups/workspaces REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/groups)
- [Power BI reports REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/reports)
- [Power BI datasets REST API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets)
- [Fabric semantic model REST API](https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/get-semantic-model)
- [Power BI XMLA endpoint docs](https://learn.microsoft.com/en-us/fabric/enterprise/powerbi/service-premium-connect-tools)
- [Analysis Services client libraries](https://learn.microsoft.com/en-us/analysis-services/client-libraries?view=asallproducts-allversions)
