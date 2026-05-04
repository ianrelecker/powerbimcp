from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv

load_dotenv()

FABRIC_RESOURCE = "fabric"
POWERBI_RESOURCE = "powerbi"
XMLA_WRITE_CONFIRMATION = "I_UNDERSTAND_XMLA_WRITES_CAN_CHANGE_SEMANTIC_MODELS"

FABRIC_SCOPE_PREFIX = "https://api.fabric.microsoft.com/"
POWERBI_SCOPE_PREFIX = "https://analysis.windows.net/powerbi/api/"

DEFAULT_OPENID_SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
]

DEFAULT_POWERBI_RESOURCE_SCOPES = [
    f"{POWERBI_SCOPE_PREFIX}Workspace.Read.All",
    f"{POWERBI_SCOPE_PREFIX}Dashboard.Read.All",
    f"{POWERBI_SCOPE_PREFIX}Report.Read.All",
    f"{POWERBI_SCOPE_PREFIX}Dataset.ReadWrite.All",
]

DEFAULT_FABRIC_RESOURCE_SCOPES = [
    f"{FABRIC_SCOPE_PREFIX}Workspace.Read.All",
    f"{FABRIC_SCOPE_PREFIX}SemanticModel.Read.All",
]

DEFAULT_POWERBI_SCOPES = (
    DEFAULT_OPENID_SCOPES
    + DEFAULT_POWERBI_RESOURCE_SCOPES
    + DEFAULT_FABRIC_RESOURCE_SCOPES
)


def _require_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _optional_comma_list(value: str | None) -> list[str]:
    if not value:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_encryption_key(env: Mapping[str, str], name: str) -> bytes:
    value = _require_env(env, name)
    try:
        key = base64.b64decode(value, validate=True)
    except Exception as exc:  # pragma: no cover - exact decoder errors vary
        raise ValueError(f"{name} must be a base64-encoded 32-byte key") from exc

    if len(key) != 32:
        raise ValueError(f"{name} must be a base64-encoded 32-byte key")

    return key


def _parse_url(value: str, *, name: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{name} must be a valid absolute URL")
    return value


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_scopes(
    source: Mapping[str, str],
) -> tuple[list[str], list[str], list[str]]:
    oidc_scopes = _optional_comma_list(source.get("OPENID_SCOPES")) or DEFAULT_OPENID_SCOPES
    powerbi_scopes: list[str] = []
    fabric_scopes: list[str] = []

    for scope in _optional_comma_list(source.get("POWERBI_SCOPES")):
        normalized = scope.lower()
        if normalized in {item.lower() for item in DEFAULT_OPENID_SCOPES}:
            if scope not in oidc_scopes:
                oidc_scopes.append(scope)
        elif normalized.startswith(FABRIC_SCOPE_PREFIX.lower()):
            fabric_scopes.append(scope)
        else:
            powerbi_scopes.append(scope)

    fabric_scopes.extend(_optional_comma_list(source.get("FABRIC_SCOPES")))

    return (
        oidc_scopes,
        powerbi_scopes or DEFAULT_POWERBI_RESOURCE_SCOPES,
        fabric_scopes or DEFAULT_FABRIC_RESOURCE_SCOPES,
    )


@dataclass(frozen=True)
class EntraConfig:
    tenantId: str
    clientId: str
    clientSecret: str
    redirectUri: str
    oidcScopes: list[str]
    powerbiScopes: list[str]
    fabricScopes: list[str]

    @property
    def scopes(self) -> list[str]:
        return self.oidcScopes + self.powerbiScopes + self.fabricScopes


@dataclass(frozen=True)
class AppConfig:
    port: int
    localBaseUrl: str
    entra: EntraConfig
    encryptionKey: bytes
    knownWorkspaces: list[str]
    tokenFile: Path
    xmlaBridgePath: Path
    xmlaTenantAlias: str
    xmlaAllowWrites: bool
    xmlaBridgeTimeoutSeconds: int


def build_config_from_env(env: Mapping[str, str] | None = None) -> AppConfig:
    source = dict(os.environ if env is None else env)
    port = int(source.get("PORT", "8787"))
    local_base_url = _parse_url(
        source.get("LOCAL_BASE_URL", f"http://localhost:{port}"),
        name="LOCAL_BASE_URL",
    )
    oidc_scopes, powerbi_scopes, fabric_scopes = _parse_scopes(source)
    default_bridge_path = (
        Path(__file__).parents[2]
        / "xmla_bridge"
        / "PowerBIXmlaBridge"
        / "PowerBIXmlaBridge.csproj"
    )

    return AppConfig(
        port=port,
        localBaseUrl=local_base_url,
        entra=EntraConfig(
            tenantId=_require_env(source, "POWERBI_TENANT_ID"),
            clientId=_require_env(source, "POWERBI_CLIENT_ID"),
            clientSecret=_require_env(source, "POWERBI_CLIENT_SECRET"),
            redirectUri=urljoin(local_base_url, "/auth/microsoft/callback"),
            oidcScopes=oidc_scopes,
            powerbiScopes=powerbi_scopes,
            fabricScopes=fabric_scopes,
        ),
        encryptionKey=_parse_encryption_key(source, "TOKEN_ENCRYPTION_KEY"),
        knownWorkspaces=_optional_comma_list(source.get("KNOWN_WORKSPACES")),
        tokenFile=Path(".tokens/powerbi-token.json"),
        xmlaBridgePath=Path(source.get("XMLA_BRIDGE_PATH", default_bridge_path)),
        xmlaTenantAlias=source.get("POWERBI_XMLA_TENANT_ALIAS", "myorg"),
        xmlaAllowWrites=_parse_bool(source.get("POWERBI_XMLA_ALLOW_WRITES")),
        xmlaBridgeTimeoutSeconds=int(source.get("XMLA_BRIDGE_TIMEOUT_SECONDS", "60")),
    )


def load_config() -> AppConfig:
    return build_config_from_env()
