from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from powerbi_mcp.config import (
    DEFAULT_FABRIC_RESOURCE_SCOPES,
    DEFAULT_OPENID_SCOPES,
    DEFAULT_POWERBI_RESOURCE_SCOPES,
    AppConfig,
    EntraConfig,
)

TEST_KEY = bytes(range(32))
TEST_KEY_B64 = base64.b64encode(TEST_KEY).decode("ascii")


def make_jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    encode = lambda value: base64.urlsafe_b64encode(  # noqa: E731
        json.dumps(value, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{encode(header)}.{encode(payload)}."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def config_factory(
    tmp_path: Path,
) -> Callable[..., AppConfig]:
    def factory(**overrides: object) -> AppConfig:
        port = int(overrides.pop("port", 8787))
        local_base_url = str(
            overrides.pop("localBaseUrl", f"http://localhost:{port}")
        )
        token_file = Path(
            overrides.pop(
                "tokenFile",
                tmp_path / ".tokens" / "powerbi-token.json",
            )
        )
        entra = EntraConfig(
            tenantId=str(overrides.pop("tenantId", "tenant-id")),
            clientId=str(overrides.pop("clientId", "client-id")),
            clientSecret=str(overrides.pop("clientSecret", "client-secret")),
            redirectUri=str(
                overrides.pop(
                    "redirectUri",
                    f"{local_base_url}/auth/microsoft/callback",
                )
            ),
            oidcScopes=list(overrides.pop("oidcScopes", DEFAULT_OPENID_SCOPES)),
            powerbiScopes=list(
                overrides.pop("powerbiScopes", DEFAULT_POWERBI_RESOURCE_SCOPES)
            ),
            fabricScopes=list(
                overrides.pop("fabricScopes", DEFAULT_FABRIC_RESOURCE_SCOPES)
            ),
        )
        xmla_bridge_path = Path(
            overrides.pop(
                "xmlaBridgePath",
                Path("xmla_bridge/PowerBIXmlaBridge/PowerBIXmlaBridge.csproj"),
            )
        )
        xmla_tenant_alias = str(overrides.pop("xmlaTenantAlias", "myorg"))
        xmla_allow_writes = bool(overrides.pop("xmlaAllowWrites", False))
        xmla_bridge_timeout = int(overrides.pop("xmlaBridgeTimeoutSeconds", 60))

        if overrides:
            raise AssertionError(f"Unexpected config overrides: {sorted(overrides)}")

        return AppConfig(
            port=port,
            localBaseUrl=local_base_url,
            entra=entra,
            encryptionKey=TEST_KEY,
            knownWorkspaces=["Sales Workspace"],
            tokenFile=token_file,
            xmlaBridgePath=xmla_bridge_path,
            xmlaTenantAlias=xmla_tenant_alias,
            xmlaAllowWrites=xmla_allow_writes,
            xmlaBridgeTimeoutSeconds=xmla_bridge_timeout,
        )

    return factory
