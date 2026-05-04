from __future__ import annotations

from powerbi_mcp.config import (
    DEFAULT_FABRIC_RESOURCE_SCOPES,
    DEFAULT_OPENID_SCOPES,
    DEFAULT_POWERBI_RESOURCE_SCOPES,
    FABRIC_SCOPE_PREFIX,
    POWERBI_SCOPE_PREFIX,
    build_config_from_env,
)

from .conftest import TEST_KEY_B64


def test_build_config_parses_defaults_and_known_workspaces() -> None:
    config = build_config_from_env(
        {
            "POWERBI_TENANT_ID": "tenant",
            "POWERBI_CLIENT_ID": "client",
            "POWERBI_CLIENT_SECRET": "secret",
            "TOKEN_ENCRYPTION_KEY": TEST_KEY_B64,
            "KNOWN_WORKSPACES": " Sales Workspace , Finance Workspace ",
        }
    )

    assert config.port == 8787
    assert config.localBaseUrl == "http://localhost:8787"
    assert config.entra.redirectUri == "http://localhost:8787/auth/microsoft/callback"
    assert config.knownWorkspaces == ["Sales Workspace", "Finance Workspace"]
    assert config.encryptionKey == bytes(range(32))
    assert config.entra.oidcScopes == DEFAULT_OPENID_SCOPES
    assert config.entra.powerbiScopes == DEFAULT_POWERBI_RESOURCE_SCOPES
    assert config.entra.fabricScopes == DEFAULT_FABRIC_RESOURCE_SCOPES
    assert f"{POWERBI_SCOPE_PREFIX}Dashboard.Read.All" in config.entra.powerbiScopes
    assert f"{POWERBI_SCOPE_PREFIX}Dataset.ReadWrite.All" in config.entra.powerbiScopes
    assert f"{FABRIC_SCOPE_PREFIX}Workspace.Read.All" in config.entra.fabricScopes
    assert f"{FABRIC_SCOPE_PREFIX}SemanticModel.Read.All" in config.entra.fabricScopes
    assert config.xmlaTenantAlias == "myorg"
    assert config.xmlaAllowWrites is False


def test_build_config_splits_scope_overrides_by_resource() -> None:
    config = build_config_from_env(
        {
            "POWERBI_TENANT_ID": "tenant",
            "POWERBI_CLIENT_ID": "client",
            "POWERBI_CLIENT_SECRET": "secret",
            "TOKEN_ENCRYPTION_KEY": TEST_KEY_B64,
            "POWERBI_SCOPES": "openid, offline_access, https://analysis.windows.net/powerbi/api/Dashboard.Read.All, https://api.fabric.microsoft.com/SemanticModel.Read.All",
            "POWERBI_XMLA_TENANT_ALIAS": "contoso.com",
            "POWERBI_XMLA_ALLOW_WRITES": "true",
        }
    )

    assert "openid" in config.entra.oidcScopes
    assert "offline_access" in config.entra.oidcScopes
    assert config.entra.powerbiScopes == [
        "https://analysis.windows.net/powerbi/api/Dashboard.Read.All"
    ]
    assert config.entra.fabricScopes == [
        "https://api.fabric.microsoft.com/SemanticModel.Read.All"
    ]
    assert config.xmlaTenantAlias == "contoso.com"
    assert config.xmlaAllowWrites is True


def test_build_config_rejects_invalid_encryption_key() -> None:
    try:
        build_config_from_env(
            {
                "POWERBI_TENANT_ID": "tenant",
                "POWERBI_CLIENT_ID": "client",
                "POWERBI_CLIENT_SECRET": "secret",
                "TOKEN_ENCRYPTION_KEY": "not-base64",
            }
        )
    except ValueError as error:
        assert "TOKEN_ENCRYPTION_KEY" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected invalid encryption key to fail")
