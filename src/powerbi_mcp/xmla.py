from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from .config import (
    POWERBI_RESOURCE,
    XMLA_WRITE_CONFIRMATION,
    AppConfig,
)
from .fabric_api import FabricClient
from .microsoft_auth import MicrosoftAuthService
from .models import (
    SemanticModelInfo,
    WorkspaceInfo,
    XmlaAttachResult,
    XmlaExecuteResult,
    XmlaQueryResult,
)
from .powerbi_api import PowerBIClient


XMLA_REQUIREMENTS = [
    "Workspace must be backed by Power BI Premium, Premium Per User, Power BI Embedded, or Fabric capacity.",
    "Capacity XMLA Endpoint setting must allow Read Write for write commands.",
    "Tenant XMLA endpoint settings must allow the signed-in account.",
    "Read requires semantic model Build permission; write requires Contributor or higher workspace/model permissions.",
]


class XMLABridgeRunner:
    def __init__(self, bridge_path: Path, *, timeout_seconds: int = 60) -> None:
        self._bridge_path = bridge_path
        self._timeout_seconds = timeout_seconds

    async def run(
        self,
        payload: dict[str, Any],
        *,
        access_token: str,
        expires_at: int,
    ) -> dict[str, Any]:
        command = self._command()
        request = {
            **payload,
            "accessToken": access_token,
            "accessTokenExpiresAt": expires_at,
        }

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "XMLA bridge could not be started. Install the .NET SDK/runtime "
                f"and verify XMLA_BRIDGE_PATH points to {self._bridge_path}."
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(request).encode("utf-8")),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError(
                f"XMLA bridge timed out after {self._timeout_seconds} seconds"
            ) from exc

        stdout_text = self._sanitize(stdout.decode("utf-8", errors="replace"), access_token)
        stderr_text = self._sanitize(stderr.decode("utf-8", errors="replace"), access_token)

        if process.returncode != 0:
            message = stderr_text.strip() or stdout_text.strip() or "no output"
            raise RuntimeError(f"XMLA bridge failed: {message}")

        try:
            result = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"XMLA bridge returned invalid JSON: {stdout_text.strip() or stderr_text.strip()}"
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError("XMLA bridge returned an unexpected response")

        if result.get("success") is False:
            raise RuntimeError(str(result.get("error") or "XMLA bridge command failed"))

        data = result.get("data", result)
        if not isinstance(data, dict):
            raise RuntimeError("XMLA bridge returned an unexpected data payload")
        return data

    def _command(self) -> list[str]:
        path = self._bridge_path
        if path.suffix.lower() == ".dll":
            return ["dotnet", str(path)]
        if path.suffix.lower() == ".csproj":
            return ["dotnet", "run", "--project", str(path), "--"]
        if path.is_dir():
            project_files = sorted(path.glob("*.csproj"))
            if project_files:
                return ["dotnet", "run", "--project", str(project_files[0]), "--"]
        return [str(path)]

    def _sanitize(self, value: str, access_token: str) -> str:
        if not access_token:
            return value
        return value.replace(access_token, "[redacted]")


class PowerBIXMLAClient:
    def __init__(
        self,
        config: AppConfig,
        auth_service: MicrosoftAuthService,
        powerbi: PowerBIClient,
        fabric: FabricClient,
        bridge_runner: XMLABridgeRunner | None = None,
    ) -> None:
        self._config = config
        self._auth_service = auth_service
        self._powerbi = powerbi
        self._fabric = fabric
        self._bridge_runner = bridge_runner or XMLABridgeRunner(
            config.xmlaBridgePath,
            timeout_seconds=config.xmlaBridgeTimeoutSeconds,
        )

    async def attach(
        self,
        *,
        workspaceId: str,
        semanticModelId: str | None = None,
        semanticModelName: str | None = None,
        tenantAlias: str | None = None,
        validate: bool = True,
    ) -> XmlaAttachResult:
        workspace = (await self._powerbi.get_workspace(workspaceId=workspaceId)).workspace
        semantic_model = await self._resolve_semantic_model(
            workspaceId=workspaceId,
            semanticModelId=semanticModelId,
            semanticModelName=semanticModelName,
        )
        tenant = tenantAlias or self._config.xmlaTenantAlias
        candidates = self._attach_candidates(workspace, semantic_model, tenant)
        primary = candidates[0]
        result = XmlaAttachResult(
            workspaceId=workspace.id,
            workspaceName=workspace.name,
            semanticModelId=semantic_model.id,
            semanticModelName=semantic_model.displayName,
            tenantAlias=tenant,
            serverUrl=primary["serverUrl"],
            initialCatalog=primary["initialCatalog"],
            alternateServerUrl=candidates[-1]["serverUrl"] if len(candidates) > 1 else None,
            alternateInitialCatalog=(
                candidates[-1]["initialCatalog"] if len(candidates) > 1 else None
            ),
            effectiveServerUrl=primary["serverUrl"],
            effectiveInitialCatalog=primary["initialCatalog"],
            validated=False,
            writeEnabled=self._config.xmlaAllowWrites,
            requirements=XMLA_REQUIREMENTS,
        )

        if not validate:
            return result

        access_token = await self._auth_service.get_access_token_record(POWERBI_RESOURCE)
        last_error: str | None = None
        for candidate in candidates:
            try:
                await self._bridge_runner.run(
                    {
                        "command": "attach",
                        "serverUrl": candidate["serverUrl"],
                        "initialCatalog": candidate["initialCatalog"],
                    },
                    access_token=access_token.accessToken,
                    expires_at=access_token.expiresAt,
                )
                return result.model_copy(
                    update={
                        "effectiveServerUrl": candidate["serverUrl"],
                        "effectiveInitialCatalog": candidate["initialCatalog"],
                        "validated": True,
                        "validationError": None,
                    }
                )
            except Exception as error:
                last_error = str(error)

        return result.model_copy(update={"validationError": last_error})

    async def query(
        self,
        *,
        workspaceId: str,
        query: str,
        semanticModelId: str | None = None,
        semanticModelName: str | None = None,
        queryType: Literal["dax", "mdx", "dmv"] = "dax",
        tenantAlias: str | None = None,
        maxRows: int = 500,
    ) -> XmlaQueryResult:
        attach = await self.attach(
            workspaceId=workspaceId,
            semanticModelId=semanticModelId,
            semanticModelName=semanticModelName,
            tenantAlias=tenantAlias,
            validate=True,
        )
        if not attach.validated:
            raise RuntimeError(f"XMLA attach validation failed: {attach.validationError}")

        access_token = await self._auth_service.get_access_token_record(POWERBI_RESOURCE)
        result = await self._bridge_runner.run(
            {
                "command": "query",
                "serverUrl": attach.effectiveServerUrl,
                "initialCatalog": attach.effectiveInitialCatalog,
                "query": query,
                "queryType": queryType,
                "maxRows": min(max(maxRows, 1), 5000),
            },
            access_token=access_token.accessToken,
            expires_at=access_token.expiresAt,
        )

        return XmlaQueryResult(
            attach=attach,
            queryType=queryType,
            columns=list(result.get("columns", [])),
            rows=list(result.get("rows", [])),
            rowCount=int(result.get("rowCount", 0)),
            truncated=bool(result.get("truncated", False)),
        )

    async def execute(
        self,
        *,
        workspaceId: str,
        commandText: str,
        semanticModelId: str | None = None,
        semanticModelName: str | None = None,
        commandType: Literal["xmla", "tmsl"] = "xmla",
        tenantAlias: str | None = None,
        confirmation: str | None = None,
    ) -> XmlaExecuteResult:
        if not self._config.xmlaAllowWrites:
            raise RuntimeError(
                "XMLA writes are disabled. Set POWERBI_XMLA_ALLOW_WRITES=true to enable them."
            )
        if confirmation != XMLA_WRITE_CONFIRMATION:
            raise RuntimeError(
                f"XMLA writes require confirmation: {XMLA_WRITE_CONFIRMATION}"
            )

        attach = await self.attach(
            workspaceId=workspaceId,
            semanticModelId=semanticModelId,
            semanticModelName=semanticModelName,
            tenantAlias=tenantAlias,
            validate=True,
        )
        if not attach.validated:
            raise RuntimeError(f"XMLA attach validation failed: {attach.validationError}")

        access_token = await self._auth_service.get_access_token_record(POWERBI_RESOURCE)
        result = await self._bridge_runner.run(
            {
                "command": "execute",
                "serverUrl": attach.effectiveServerUrl,
                "initialCatalog": attach.effectiveInitialCatalog,
                "commandText": commandText,
                "commandType": commandType,
            },
            access_token=access_token.accessToken,
            expires_at=access_token.expiresAt,
        )

        return XmlaExecuteResult(
            attach=attach,
            commandType=commandType,
            executed=bool(result.get("executed", False)),
            messages=list(result.get("messages", [])),
            results=list(result.get("results", [])),
        )

    async def _resolve_semantic_model(
        self,
        *,
        workspaceId: str,
        semanticModelId: str | None,
        semanticModelName: str | None,
    ) -> SemanticModelInfo:
        if bool(semanticModelId) == bool(semanticModelName):
            raise RuntimeError("Pass exactly one of semanticModelId or semanticModelName")

        if semanticModelId:
            return (
                await self._fabric.get_semantic_model(
                    workspaceId=workspaceId,
                    semanticModelId=semanticModelId,
                )
            ).semanticModel

        listed = await self._fabric.list_semantic_models(workspaceId=workspaceId)
        matches = [
            model
            for model in listed.semanticModels
            if model.displayName.casefold() == str(semanticModelName).casefold()
        ]
        if not matches:
            raise RuntimeError(f"Semantic model was not found: {semanticModelName}")
        if len(matches) > 1:
            ids = ", ".join(model.id for model in matches)
            raise RuntimeError(
                f"Semantic model name is ambiguous; pass semanticModelId. Matching IDs: {ids}"
            )
        return matches[0]

    def _attach_candidates(
        self,
        workspace: WorkspaceInfo,
        semantic_model: SemanticModelInfo,
        tenant_alias: str,
    ) -> list[dict[str, str]]:
        workspace_refs = [
            workspace.name,
            f"{workspace.name} - {workspace.id}",
        ]
        catalog_refs = [
            semantic_model.displayName,
            f"{semantic_model.displayName} - {semantic_model.id}",
        ]
        candidates: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for workspace_ref in workspace_refs:
            for catalog_ref in catalog_refs:
                server_url = self._server_url(tenant_alias, workspace_ref)
                key = (server_url, catalog_ref)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    {
                        "serverUrl": server_url,
                        "initialCatalog": catalog_ref,
                    }
                )
        return candidates

    def _server_url(self, tenant_alias: str, workspace_reference: str) -> str:
        tenant = quote(tenant_alias.strip(), safe="")
        workspace = quote(workspace_reference.strip(), safe="")
        return f"powerbi://api.powerbi.com/v1.0/{tenant}/{workspace}"
