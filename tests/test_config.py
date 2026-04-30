from __future__ import annotations

from powerbi_mcp.config import (
    DEFAULT_POWERBI_SCOPES,
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
    assert config.entra.scopes == DEFAULT_POWERBI_SCOPES
    assert f"{POWERBI_SCOPE_PREFIX}Dashboard.Read.All" in config.entra.scopes
    assert f"{POWERBI_SCOPE_PREFIX}Dataset.Read.All" in config.entra.scopes


def test_build_config_allows_scope_override() -> None:
    config = build_config_from_env(
        {
            "POWERBI_TENANT_ID": "tenant",
            "POWERBI_CLIENT_ID": "client",
            "POWERBI_CLIENT_SECRET": "secret",
            "TOKEN_ENCRYPTION_KEY": TEST_KEY_B64,
            "POWERBI_SCOPES": "openid, offline_access, https://analysis.windows.net/powerbi/api/Dashboard.Read.All",
        }
    )

    assert config.entra.scopes == [
        "openid",
        "offline_access",
        "https://analysis.windows.net/powerbi/api/Dashboard.Read.All",
    ]


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
