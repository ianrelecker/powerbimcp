from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx

from .config import FABRIC_RESOURCE
from .microsoft_auth import MicrosoftAuthService
from .models import (
    SemanticModelInfo,
    SemanticModelListResult,
    SemanticModelResult,
)


FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"


class FabricClient:
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

    async def list_semantic_models(
        self,
        *,
        workspaceId: str,
        continuationToken: str | None = None,
        recursive: bool = True,
        rootFolderId: str | None = None,
    ) -> SemanticModelListResult:
        params: dict[str, str] = {"recursive": str(recursive).lower()}
        if continuationToken:
            params["continuationToken"] = continuationToken
        if rootFolderId:
            params["rootFolderId"] = rootFolderId

        result = await self._request(
            f"/workspaces/{self._segment(workspaceId)}/semanticModels?{httpx.QueryParams(params)}"
        )
        return SemanticModelListResult(
            workspaceId=workspaceId,
            semanticModels=[
                self._map_semantic_model(item) for item in result.get("value", [])
            ],
            continuationToken=result.get("continuationToken"),
            continuationUri=result.get("continuationUri"),
        )

    async def get_semantic_model(
        self,
        *,
        workspaceId: str,
        semanticModelId: str,
    ) -> SemanticModelResult:
        result = await self._request(
            f"/workspaces/{self._segment(workspaceId)}/semanticModels/{self._segment(semanticModelId)}"
        )
        return SemanticModelResult(
            workspaceId=workspaceId,
            semanticModel=self._map_semantic_model(result),
        )

    async def _request(self, path: str) -> dict[str, Any]:
        token = await self._auth_service.get_access_token(FABRIC_RESOURCE)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        async with self._client() as client:
            response = await client.get(self._url(path), headers=headers)

        if not response.is_success:
            raise RuntimeError(self._format_error(response, "GET", path))

        if not response.content:
            return {}

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(
                f"Fabric API returned an unexpected response for GET {path}"
            )
        return data

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return FABRIC_API_BASE + (path if path.startswith("/") else f"/{path}")

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
            f"Fabric API request failed ({method} {path}): "
            f"{response.status_code} {response.reason_phrase}: {detail}"
        )

    def _map_semantic_model(self, data: dict[str, Any]) -> SemanticModelInfo:
        return SemanticModelInfo.model_validate(data)
