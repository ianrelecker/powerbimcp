from __future__ import annotations

import httpx
import pytest

from powerbi_mcp.config import FABRIC_RESOURCE
from powerbi_mcp.fabric_api import FabricClient


class StaticAuthService:
    async def get_access_token(self, resource: str = FABRIC_RESOURCE) -> str:
        assert resource == FABRIC_RESOURCE
        return "fabric-token"


@pytest.mark.anyio
async def test_list_and_get_semantic_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer fabric-token"

        if request.url.path.endswith("/workspaces/workspace-1/semanticModels"):
            assert request.url.params["recursive"] == "true"
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "semantic-1",
                            "displayName": "Sales Model",
                            "description": "Model description",
                            "type": "SemanticModel",
                            "workspaceId": "workspace-1",
                        }
                    ],
                    "continuationToken": "next-token",
                },
            )

        if request.url.path.endswith("/workspaces/workspace-1/semanticModels/semantic-1"):
            return httpx.Response(
                200,
                json={
                    "id": "semantic-1",
                    "displayName": "Sales Model",
                    "type": "SemanticModel",
                    "workspaceId": "workspace-1",
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fabric = FabricClient(StaticAuthService(), client)

    listed = await fabric.list_semantic_models(workspaceId="workspace-1")
    assert listed.semanticModels[0].displayName == "Sales Model"
    assert listed.continuationToken == "next-token"

    model = await fabric.get_semantic_model(
        workspaceId="workspace-1",
        semanticModelId="semantic-1",
    )
    assert model.semanticModel.id == "semantic-1"

    await client.aclose()
