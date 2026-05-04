from __future__ import annotations

import base64
import json
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import httpx

from .config import (
    FABRIC_RESOURCE,
    FABRIC_SCOPE_PREFIX,
    POWERBI_RESOURCE,
    POWERBI_SCOPE_PREFIX,
    AppConfig,
)
from .models import (
    AccountInfo,
    MicrosoftConnectionStatus,
    ResourceScopeStatus,
    StoredMicrosoftTokens,
    StoredResourceToken,
)
from .token_store import EncryptedFileStore


def decode_id_claims(id_token: str | None) -> dict[str, Any] | None:
    if not id_token:
        return None

    parts = id_token.split(".")
    if len(parts) < 2:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        claims = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(claims, dict):
        return None
    return claims


class MicrosoftAuthService:
    def __init__(
        self,
        config: AppConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._token_store = EncryptedFileStore(config.tokenFile, config.encryptionKey)
        self._http_client = http_client
        self._pending_state: str | None = None

    @asynccontextmanager
    async def _client(self) -> Any:
        if self._http_client is not None:
            yield self._http_client
            return

        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
            yield client

    def build_authorization_url(self) -> str:
        state = str(uuid4())
        self._pending_state = state

        request = httpx.URL(
            f"https://login.microsoftonline.com/{self._config.entra.tenantId}/oauth2/v2.0/authorize"
        )
        return str(
            request.copy_add_param("client_id", self._config.entra.clientId)
            .copy_add_param("response_type", "code")
            .copy_add_param("redirect_uri", self._config.entra.redirectUri)
            .copy_add_param("response_mode", "query")
            .copy_add_param("scope", " ".join(self._config.entra.scopes))
            .copy_add_param("state", state)
        )

    async def handle_authorization_code_callback(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
        errorDescription: str | None,
    ) -> None:
        if error:
            raise RuntimeError(
                f"Microsoft sign-in failed: {errorDescription or error}"
            )

        if not code or not state:
            raise RuntimeError("Microsoft callback is missing the code or state parameter")

        if not self._pending_state or state != self._pending_state:
            raise RuntimeError("Microsoft callback state was invalid")

        self._pending_state = None

        token_response = await self._fetch_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._config.entra.redirectUri,
                "scope": " ".join(
                    self._resource_scopes(POWERBI_RESOURCE, include_oidc=True)
                ),
            }
        )

        refresh_token = token_response.get("refresh_token")
        if not refresh_token:
            raise RuntimeError(
                "Microsoft did not return a refresh token. Make sure offline_access is granted."
            )

        await self._save_token_response(
            token_response,
            refresh_token,
            resource=POWERBI_RESOURCE,
        )

        try:
            await self.get_access_token(FABRIC_RESOURCE)
        except Exception:
            # Status reports the missing Fabric token separately; keep the base
            # Power BI connection usable when only that consent succeeds.
            return

    async def get_access_token(self, resource: str = POWERBI_RESOURCE) -> str:
        token = await self.get_access_token_record(resource)
        return token.accessToken

    async def get_access_token_record(
        self,
        resource: str = POWERBI_RESOURCE,
    ) -> StoredResourceToken:
        tokens = await self._load_tokens()
        if tokens is None:
            raise RuntimeError(
                "Power BI is not connected yet. Visit /auth/microsoft/start first."
            )

        existing_token = self._resource_token(tokens, resource)
        if (
            existing_token is not None
            and existing_token.expiresAt > int(time.time() * 1000) + 60_000
        ):
            return existing_token

        refreshed = await self._fetch_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": tokens.refreshToken,
                "scope": " ".join(self._resource_scopes(resource)),
            }
        )

        saved = await self._save_token_response(
            refreshed,
            refreshed.get("refresh_token") or tokens.refreshToken,
            resource=resource,
        )
        token = self._resource_token(saved, resource)
        if token is None:  # pragma: no cover - defensive
            raise RuntimeError(f"Microsoft did not return a {resource} access token")
        return token

    async def disconnect(self) -> None:
        await self._token_store.clear()

    async def get_status(self) -> MicrosoftConnectionStatus:
        tokens = await self._load_tokens()
        resource_statuses = [
            self._resource_status(resource, tokens)
            for resource in (POWERBI_RESOURCE, FABRIC_RESOURCE)
        ]
        required_scopes = [
            scope
            for status in resource_statuses
            for scope in status.requiredScopes
        ]
        granted_scopes = [
            scope
            for status in resource_statuses
            for scope in status.grantedScopes
        ]
        missing_scopes = [
            scope
            for status in resource_statuses
            for scope in status.missingScopes
        ]
        expires_at_values = [
            status.expiresAt
            for status in resource_statuses
            if status.expiresAt is not None
        ]

        return MicrosoftConnectionStatus(
            connected=tokens is not None,
            account=tokens.account if tokens else None,
            expiresAt=min(expires_at_values) if expires_at_values else None,
            knownWorkspaces=self._config.knownWorkspaces,
            requiredScopes=required_scopes,
            grantedScopes=granted_scopes,
            missingScopes=missing_scopes,
            resourceStatuses=resource_statuses,
        )

    async def _load_tokens(self) -> StoredMicrosoftTokens | None:
        raw = await self._token_store.load()
        if not raw:
            return None

        tokens = StoredMicrosoftTokens.model_validate(raw)
        if tokens.accessToken and tokens.expiresAt and tokens.scope:
            tokens.accessTokens.setdefault(
                POWERBI_RESOURCE,
                StoredResourceToken(
                    accessToken=tokens.accessToken,
                    expiresAt=tokens.expiresAt,
                    scope=tokens.scope,
                    updatedAt=tokens.updatedAt,
                ),
            )
        return tokens

    async def _fetch_token(self, payload: dict[str, str]) -> dict[str, Any]:
        token_url = (
            f"https://login.microsoftonline.com/"
            f"{self._config.entra.tenantId}/oauth2/v2.0/token"
        )
        body = {
            "client_id": self._config.entra.clientId,
            "client_secret": self._config.entra.clientSecret,
            **payload,
        }

        async with self._client() as client:
            response = await client.post(
                token_url,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(
                f"Microsoft token exchange failed: {response.reason_phrase}"
            )

        if not response.is_success or data.get("error"):
            raise RuntimeError(
                "Microsoft token exchange failed: "
                f"{data.get('error_description') or data.get('error') or response.reason_phrase}"
            )

        return data

    def _resource_scopes(self, resource: str, *, include_oidc: bool = False) -> list[str]:
        scopes = list(self._config.entra.oidcScopes) if include_oidc else []
        if resource == POWERBI_RESOURCE:
            scopes.extend(self._config.entra.powerbiScopes)
        elif resource == FABRIC_RESOURCE:
            scopes.extend(self._config.entra.fabricScopes)
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unknown Microsoft token resource: {resource}")
        return scopes

    def _resource_token(
        self,
        tokens: StoredMicrosoftTokens,
        resource: str,
    ) -> StoredResourceToken | None:
        return tokens.accessTokens.get(resource)

    def _resource_status(
        self,
        resource: str,
        tokens: StoredMicrosoftTokens | None,
    ) -> ResourceScopeStatus:
        required_scopes = self._resource_scopes(resource)
        token = self._resource_token(tokens, resource) if tokens is not None else None
        granted_scopes = self._parse_scope_string(token.scope) if token else []

        return ResourceScopeStatus(
            resource=resource,
            connected=token is not None,
            expiresAt=token.expiresAt if token else None,
            requiredScopes=required_scopes,
            grantedScopes=granted_scopes,
            missingScopes=(
                required_scopes
                if token is None
                else self._missing_scopes(required_scopes, granted_scopes)
            ),
        )

    def _parse_scope_string(self, value: str) -> list[str]:
        return [scope for scope in value.split() if scope]

    def _missing_scopes(
        self,
        required_scopes: list[str],
        granted_scopes: list[str],
    ) -> list[str]:
        return [
            scope
            for scope in required_scopes
            if not self._scope_was_granted(scope, granted_scopes)
        ]

    def _scope_was_granted(self, required_scope: str, granted_scopes: list[str]) -> bool:
        required = self._normalize_scope(required_scope)
        granted = {self._normalize_scope(scope) for scope in granted_scopes}
        return required in granted

    def _normalize_scope(self, scope: str) -> str:
        normalized = scope.lower()
        for prefix in (POWERBI_SCOPE_PREFIX.lower(), FABRIC_SCOPE_PREFIX.lower()):
            if normalized.startswith(prefix):
                return normalized.removeprefix(prefix)
        return normalized

    async def _save_token_response(
        self,
        token_response: dict[str, Any],
        refresh_token: str,
        *,
        resource: str,
    ) -> StoredMicrosoftTokens:
        existing = await self._load_tokens()
        claims = decode_id_claims(
            token_response.get("id_token")
            if isinstance(token_response.get("id_token"), str)
            else None,
        )
        expires_in = int(token_response.get("expires_in", 3600))
        expires_at = int(time.time() * 1000) + expires_in * 1000

        account = (
            AccountInfo(
                name=claims.get("name") if claims else None,
                preferredUsername=(
                    claims.get("preferred_username")
                    or claims.get("upn")
                    or claims.get("email")
                )
                if claims
                else None,
                oid=claims.get("oid") if claims else None,
                tid=claims.get("tid") if claims else None,
            )
            if claims
            else existing.account
            if existing
            else None
        )
        access_tokens = dict(existing.accessTokens) if existing else {}
        updated_at = int(time.time() * 1000)
        access_tokens[resource] = StoredResourceToken(
            accessToken=str(token_response["access_token"]),
            expiresAt=expires_at,
            scope=str(token_response.get("scope") or " ".join(self._resource_scopes(resource))),
            updatedAt=updated_at,
        )

        tokens = StoredMicrosoftTokens(
            refreshToken=refresh_token,
            accessTokens=access_tokens,
            idToken=(
                str(token_response["id_token"])
                if token_response.get("id_token") is not None
                else existing.idToken
                if existing
                else None
            ),
            account=account,
            updatedAt=updated_at,
        )

        await self._token_store.save(
            tokens.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        return tokens
