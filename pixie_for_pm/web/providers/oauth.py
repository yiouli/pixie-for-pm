from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from pixie_for_pm.config.settings import AppSettings
from pixie_for_pm.integrations.registry import PROVIDERS


@dataclass(frozen=True)
class OAuthState:
    provider: str
    server_id: str
    user_id: str
    nonce: str


class InvalidOAuthStateError(Exception):
    """Raised when the OAuth state parameter fails signature validation."""


class OAuthProviderError(Exception):
    """Raised when the provider authorize or token flow fails."""


class OAuthService(Protocol):
    def build_state(self, *, provider: str, server_id: str, user_id: str) -> str: ...

    def parse_state(self, state: str) -> OAuthState: ...

    def get_authorize_url(self, provider: str, state: str) -> str: ...

    async def exchange_code(
        self,
        provider: str,
        code: str,
    ) -> tuple[dict[str, str], list[str] | None]: ...


class OAuthStateCodec:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()

    def encode(self, state: OAuthState) -> str:
        payload = json.dumps(
            {
                "provider": state.provider,
                "server_id": state.server_id,
                "user_id": state.user_id,
                "nonce": state.nonce,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return (
            f"{self._urlsafe_b64encode(payload)}.{self._urlsafe_b64encode(signature)}"
        )

    def decode(self, encoded_state: str) -> OAuthState:
        payload_part, signature_part = encoded_state.split(".", 1)
        payload = self._urlsafe_b64decode(payload_part)
        signature = self._urlsafe_b64decode(signature_part)
        expected_signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise InvalidOAuthStateError("OAuth state signature validation failed.")
        data = json.loads(payload.decode())
        if not isinstance(data, dict):
            raise InvalidOAuthStateError("OAuth state payload must be an object.")
        return OAuthState(
            provider=str(data["provider"]),
            server_id=str(data["server_id"]),
            user_id=str(data["user_id"]),
            nonce=str(data["nonce"]),
        )

    @staticmethod
    def _urlsafe_b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    @staticmethod
    def _urlsafe_b64decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}".encode())


class StaticOAuthService:
    def __init__(
        self,
        authorize_urls: dict[str, str],
        token_payloads: dict[str, dict[str, str]],
        *,
        state_secret: str = "pixie-test-state-secret",
    ) -> None:
        self._authorize_urls = authorize_urls
        self._token_payloads = token_payloads
        self._codec = OAuthStateCodec(state_secret)

    def build_state(self, *, provider: str, server_id: str, user_id: str) -> str:
        return self._codec.encode(
            OAuthState(
                provider=provider,
                server_id=server_id,
                user_id=user_id,
                nonce=token_urlsafe(12),
            )
        )

    def parse_state(self, state: str) -> OAuthState:
        return self._codec.decode(state)

    def get_authorize_url(self, provider: str, state: str) -> str:
        base_url = self._authorize_urls[provider]
        return _append_query_parameters(base_url, {"state": state})

    async def exchange_code(
        self,
        provider: str,
        code: str,
    ) -> tuple[dict[str, str], list[str] | None]:
        del code
        payload = self._token_payloads.get(provider)
        if payload is None:
            raise OAuthProviderError(
                f"No token payload configured for provider '{provider}'."
            )
        return payload, None


class HttpOAuthService:
    def __init__(self, settings: AppSettings) -> None:
        secret = settings.credentials_encryption_key or settings.session_secret_key
        if secret is None:
            raise ValueError("OAuth state signing requires a configured secret.")
        self._settings = settings
        self._codec = OAuthStateCodec(secret)

    def build_state(self, *, provider: str, server_id: str, user_id: str) -> str:
        return self._codec.encode(
            OAuthState(
                provider=provider,
                server_id=server_id,
                user_id=user_id,
                nonce=token_urlsafe(24),
            )
        )

    def parse_state(self, state: str) -> OAuthState:
        return self._codec.decode(state)

    def get_authorize_url(self, provider: str, state: str) -> str:
        config = PROVIDERS.get(provider)
        client_id = self._settings.oauth_client_ids.get(provider)
        if (
            config is None
            or config.auth_type != "oauth2"
            or config.oauth_authorize_url is None
        ):
            raise OAuthProviderError(f"Unsupported OAuth provider '{provider}'.")
        if client_id is None:
            raise OAuthProviderError(
                f"Missing OAuth client ID for provider '{provider}'."
            )

        query: dict[str, str] = {"client_id": client_id, "state": state}
        if self._settings.oauth_callback_url is not None:
            query["redirect_uri"] = self._settings.oauth_callback_url
        if provider == "notion":
            query["owner"] = "user"
        if config.scopes:
            query["scope"] = " ".join(config.scopes)
        query["response_type"] = "code"
        return _append_query_parameters(config.oauth_authorize_url, query)

    async def exchange_code(
        self,
        provider: str,
        code: str,
    ) -> tuple[dict[str, str], list[str] | None]:
        config = PROVIDERS.get(provider)
        client_id = self._settings.oauth_client_ids.get(provider)
        client_secret = self._settings.oauth_client_secrets.get(provider)
        if config is None or config.oauth_token_url is None:
            raise OAuthProviderError(f"Unsupported OAuth provider '{provider}'.")
        if client_id is None or client_secret is None:
            raise OAuthProviderError(
                f"Missing OAuth credentials for provider '{provider}'."
            )

        payload = {
            "grant_type": "authorization_code",
            "code": code,
        }
        if self._settings.oauth_callback_url is not None:
            payload["redirect_uri"] = self._settings.oauth_callback_url

        headers = {"Accept": "application/json"}
        if provider == "notion":
            basic_auth = base64.b64encode(
                f"{client_id}:{client_secret}".encode()
            ).decode()
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Basic {basic_auth}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    config.oauth_token_url,
                    json=payload,
                    headers=headers,
                )
        else:
            payload["client_id"] = client_id
            payload["client_secret"] = client_secret
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    config.oauth_token_url,
                    data=payload,
                    headers=headers,
                )
        if response.status_code >= 400:
            raise OAuthProviderError(
                f"OAuth token exchange failed for provider '{provider}'."
            )

        raw_payload = response.json()
        if not isinstance(raw_payload, dict):
            raise OAuthProviderError("OAuth token response must be a JSON object.")
        payload = {
            str(key): str(value)
            for key, value in raw_payload.items()
            if value is not None
        }

        scope_value = raw_payload.get("scope")
        scopes: list[str] | None = None
        if isinstance(scope_value, str) and scope_value.strip() != "":
            scopes = [scope for scope in scope_value.split(" ") if scope]

        return payload, scopes


def _append_query_parameters(url: str, parameters: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(parameters)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
