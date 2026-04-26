from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

import httpx

from pixie_for_pm.integrations.registry import PROVIDERS


class InvalidApiKeyCredentialsError(Exception):
    """Raised when user-supplied API credentials fail validation."""


class ApiKeyValidator(Protocol):
    async def validate(self, provider: str, credentials: Mapping[str, str]) -> None: ...


class MappingApiKeyValidator(ApiKeyValidator):
    def __init__(
        self, valid_credentials: Mapping[str, Sequence[Mapping[str, str]]]
    ) -> None:
        self._valid_credentials = {
            provider: {frozenset(values.items()) for values in options}
            for provider, options in valid_credentials.items()
        }

    async def validate(self, provider: str, credentials: Mapping[str, str]) -> None:
        allowed = self._valid_credentials.get(provider, set())
        if frozenset(credentials.items()) not in allowed:
            raise InvalidApiKeyCredentialsError(
                "Credentials failed provider validation."
            )


class HttpApiKeyValidator(ApiKeyValidator):
    async def validate(self, provider: str, credentials: Mapping[str, str]) -> None:
        config = PROVIDERS.get(provider)
        if config is None or config.auth_type != "api_key":
            raise InvalidApiKeyCredentialsError(
                "Provider does not support API key auth."
            )
        required_fields = config.api_key_fields or []
        missing_fields = [
            field for field in required_fields if credentials.get(field, "") == ""
        ]
        if missing_fields:
            raise InvalidApiKeyCredentialsError(
                f"Missing API key fields: {', '.join(sorted(missing_fields))}"
            )

        if provider == "posthog":
            await self._validate_posthog(credentials)
            return
        if provider == "fireflies":
            await self._validate_fireflies(credentials)
            return

        raise InvalidApiKeyCredentialsError("Unsupported API key provider.")

    async def _validate_posthog(self, credentials: Mapping[str, str]) -> None:
        host = credentials["host"].rstrip("/")
        project_id = credentials["project_id"]
        api_key = credentials["api_key"]
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{host}/api/projects/{project_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.status_code >= 400:
            raise InvalidApiKeyCredentialsError("PostHog credentials were rejected.")

    async def _validate_fireflies(self, credentials: Mapping[str, str]) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.fireflies.ai/graphql",
                headers={"Authorization": f"Bearer {credentials['api_key']}"},
                json={"query": "query { user { userId } }"},
            )
        if response.status_code >= 400:
            raise InvalidApiKeyCredentialsError("Fireflies credentials were rejected.")
