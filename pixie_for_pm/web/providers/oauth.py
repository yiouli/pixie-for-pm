from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
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


@dataclass(frozen=True)
class OAuthMetadata:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    resource: str | None = None
    scopes_supported: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotionMcpAuthorization:
    authorize_url: str
    code_verifier: str
    client_id: str
    client_secret: str | None = None
    resource: str | None = None


class OAuthService(Protocol):
    def build_state(self, *, provider: str, server_id: str, user_id: str) -> str: ...

    def parse_state(self, state: str) -> OAuthState: ...

    def get_authorize_url(
        self,
        provider: str,
        state: str,
        *,
        redirect_uri: str | None = None,
        code_challenge: str | None = None,
    ) -> str: ...

    async def exchange_code(
        self,
        provider: str,
        code: str,
        *,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> tuple[dict[str, str], list[str] | None]: ...


def generate_pkce_code_verifier() -> str:
    return token_urlsafe(64)


def build_pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


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

    def get_authorize_url(
        self,
        provider: str,
        state: str,
        *,
        redirect_uri: str | None = None,
        code_challenge: str | None = None,
    ) -> str:
        del redirect_uri
        parameters = {"state": state}
        if code_challenge is not None:
            parameters["code_challenge"] = code_challenge
            parameters["code_challenge_method"] = "S256"
        base_url = self._authorize_urls[provider]
        return _append_query_parameters(base_url, parameters)

    async def exchange_code(
        self,
        provider: str,
        code: str,
        *,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> tuple[dict[str, str], list[str] | None]:
        del redirect_uri
        del code_verifier
        del code
        payload = self._token_payloads.get(provider)
        if payload is None:
            raise OAuthProviderError(
                f"No token payload configured for provider '{provider}'."
            )
        return payload, None


async def prepare_notion_mcp_authorization(
    *,
    state: str,
    redirect_uri: str,
    client_name: str,
    client_uri: str | None = None,
) -> NotionMcpAuthorization:
    return await _prepare_mcp_authorization(
        mcp_server_url="https://mcp.notion.com/mcp",
        state=state,
        redirect_uri=redirect_uri,
        client_name=client_name,
        client_uri=client_uri,
        prompt="consent",
    )


async def exchange_notion_mcp_code(
    *,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_id: str,
    client_secret: str | None = None,
    resource: str | None = None,
) -> tuple[dict[str, str], list[str] | None]:
    return await _exchange_mcp_code(
        mcp_server_url="https://mcp.notion.com/mcp",
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        client_id=client_id,
        client_secret=client_secret,
        resource=resource,
        provider="notion",
    )


async def refresh_notion_mcp_token(
    credentials: dict[str, str] | Mapping[str, str],
) -> tuple[dict[str, str], list[str] | None]:
    return await _refresh_mcp_token(
        mcp_server_url="https://mcp.notion.com/mcp",
        credentials=credentials,
        provider="notion",
    )


async def _prepare_mcp_authorization(
    *,
    mcp_server_url: str,
    state: str,
    redirect_uri: str,
    client_name: str,
    client_uri: str | None,
    scopes: tuple[str, ...] = (),
    prompt: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> NotionMcpAuthorization:
    metadata = await _discover_oauth_metadata(mcp_server_url)
    resolved_client_id = client_id
    resolved_client_secret = client_secret
    if resolved_client_id is None or resolved_client_id.strip() == "":
        registration = await _register_dynamic_client(
            metadata,
            redirect_uri=redirect_uri,
            client_name=client_name,
            client_uri=client_uri,
        )
        resolved_client_id = registration["client_id"]
        resolved_client_secret = registration.get("client_secret")
    code_verifier = generate_pkce_code_verifier()
    code_challenge = build_pkce_code_challenge(code_verifier)
    parameters = {
        "response_type": "code",
        "client_id": resolved_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if metadata.resource is not None:
        parameters["resource"] = metadata.resource
    if scopes:
        parameters["scope"] = " ".join(scopes)
    if prompt is not None:
        parameters["prompt"] = prompt

    authorize_url = _append_query_parameters(
        metadata.authorization_endpoint,
        parameters,
    )
    return NotionMcpAuthorization(
        authorize_url=authorize_url,
        code_verifier=code_verifier,
        client_id=resolved_client_id,
        client_secret=resolved_client_secret,
        resource=metadata.resource,
    )


async def _exchange_mcp_code(
    *,
    mcp_server_url: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_id: str,
    client_secret: str | None,
    resource: str | None,
    provider: str,
) -> tuple[dict[str, str], list[str] | None]:
    metadata = await _discover_oauth_metadata(mcp_server_url)
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if client_secret is not None:
        payload["client_secret"] = client_secret
    resolved_resource = resource or metadata.resource
    if resolved_resource is not None:
        payload["resource"] = resolved_resource

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            metadata.token_endpoint,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    if response.status_code >= 400:
        raise OAuthProviderError(
            f"OAuth token exchange failed for provider '{provider}'."
        )

    return _parse_token_response(response)


async def _refresh_mcp_token(
    *,
    mcp_server_url: str,
    credentials: dict[str, str] | Mapping[str, str],
    provider: str,
) -> tuple[dict[str, str], list[str] | None]:
    refresh_token = credentials.get("refresh_token")
    client_id = credentials.get("oauth_client_id")
    resource = credentials.get("oauth_resource")
    if refresh_token is None or client_id is None or resource is None:
        raise OAuthProviderError(
            f"OAuth refresh failed for provider '{provider}': missing hosted MCP metadata."
        )

    metadata = await _discover_oauth_metadata(mcp_server_url)
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "resource": resource,
    }
    client_secret = credentials.get("oauth_client_secret")
    if client_secret is not None:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            metadata.token_endpoint,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    if response.status_code >= 400:
        raise OAuthProviderError(f"OAuth refresh failed for provider '{provider}'.")

    return _parse_token_response(response)


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

    def get_authorize_url(
        self,
        provider: str,
        state: str,
        *,
        redirect_uri: str | None = None,
        code_challenge: str | None = None,
    ) -> str:
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
        resolved_redirect_uri = redirect_uri or self._settings.oauth_callback_url
        if resolved_redirect_uri is not None:
            query["redirect_uri"] = resolved_redirect_uri
        if code_challenge is not None:
            query["code_challenge"] = code_challenge
            query["code_challenge_method"] = "S256"
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
        *,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
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
        resolved_redirect_uri = redirect_uri or self._settings.oauth_callback_url
        if resolved_redirect_uri is not None:
            payload["redirect_uri"] = resolved_redirect_uri
        if code_verifier is not None:
            payload["code_verifier"] = code_verifier

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
        return _parse_token_response_data(raw_payload)


async def _discover_oauth_metadata(mcp_server_url: str) -> OAuthMetadata:
    protected_resource_url = _resolve_protected_resource_url(mcp_server_url)

    async with httpx.AsyncClient(timeout=15.0) as client:
        protected_resource_response = await client.get(protected_resource_url)
        if protected_resource_response.status_code >= 400:
            raise OAuthProviderError("Failed to discover OAuth protected resource.")
        protected_resource = protected_resource_response.json()
        if not isinstance(protected_resource, dict):
            raise OAuthProviderError("OAuth protected resource must be a JSON object.")

        authorization_servers = protected_resource.get("authorization_servers")
        if (
            not isinstance(authorization_servers, list)
            or not authorization_servers
            or not isinstance(authorization_servers[0], str)
        ):
            raise OAuthProviderError(
                "OAuth protected resource returned no auth server."
            )

        resource = protected_resource.get("resource")
        if resource is not None and not isinstance(resource, str):
            raise OAuthProviderError("OAuth protected resource is invalid.")
        scopes_supported_raw = protected_resource.get("scopes_supported")
        scopes_supported: tuple[str, ...] = ()
        if isinstance(scopes_supported_raw, list):
            scopes_supported = tuple(
                scope
                for scope in scopes_supported_raw
                if isinstance(scope, str) and scope.strip() != ""
            )

        metadata_url = _append_path(
            authorization_servers[0], "/.well-known/oauth-authorization-server"
        )
        metadata_response = await client.get(metadata_url)
        if metadata_response.status_code >= 400:
            raise OAuthProviderError("Failed to discover OAuth authorization server.")

    metadata_payload = metadata_response.json()
    if not isinstance(metadata_payload, dict):
        raise OAuthProviderError("OAuth authorization server metadata is invalid.")

    authorization_endpoint = metadata_payload.get("authorization_endpoint")
    token_endpoint = metadata_payload.get("token_endpoint")
    registration_endpoint = metadata_payload.get("registration_endpoint")
    if not isinstance(authorization_endpoint, str) or not isinstance(
        token_endpoint, str
    ):
        raise OAuthProviderError("OAuth authorization server metadata is incomplete.")
    if registration_endpoint is not None and not isinstance(registration_endpoint, str):
        raise OAuthProviderError("OAuth registration endpoint metadata is invalid.")

    return OAuthMetadata(
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        registration_endpoint=registration_endpoint,
        resource=(
            resource if isinstance(resource, str) and resource.strip() != "" else None
        ),
        scopes_supported=scopes_supported,
    )


async def _register_dynamic_client(
    metadata: OAuthMetadata,
    *,
    redirect_uri: str,
    client_name: str,
    client_uri: str | None,
) -> dict[str, str]:
    registration_endpoint = metadata.registration_endpoint
    if registration_endpoint is None:
        raise OAuthProviderError("OAuth server does not support client registration.")

    registration_request: dict[str, object] = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if client_uri is not None:
        registration_request["client_uri"] = client_uri

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            registration_endpoint,
            json=registration_request,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    if response.status_code >= 400:
        raise OAuthProviderError("OAuth client registration failed.")

    payload = response.json()
    if not isinstance(payload, dict):
        raise OAuthProviderError("OAuth client registration response is invalid.")
    client_id = payload.get("client_id")
    client_secret = payload.get("client_secret")
    if not isinstance(client_id, str) or client_id.strip() == "":
        raise OAuthProviderError("OAuth client registration returned no client_id.")
    result = {"client_id": client_id}
    if isinstance(client_secret, str) and client_secret.strip() != "":
        result["client_secret"] = client_secret
    return result


def _resolve_protected_resource_url(mcp_server_url: str) -> str:
    parts = urlsplit(mcp_server_url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            "/.well-known/oauth-protected-resource",
            "",
            "",
        )
    )


def _append_path(base_url: str, path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _parse_token_response(
    response: httpx.Response,
) -> tuple[dict[str, str], list[str] | None]:
    return _parse_token_response_data(response.json())


def _parse_token_response_data(
    raw_payload: object,
) -> tuple[dict[str, str], list[str] | None]:
    if not isinstance(raw_payload, dict):
        raise OAuthProviderError("OAuth token response must be a JSON object.")
    payload = {
        str(key): str(value) for key, value in raw_payload.items() if value is not None
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
