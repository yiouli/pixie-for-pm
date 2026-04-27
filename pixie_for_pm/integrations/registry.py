from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    name: str
    auth_type: Literal["oauth2", "api_key"]
    oauth_authorize_url: str | None = None
    oauth_token_url: str | None = None
    scopes: list[str] | None = None
    api_key_fields: list[str] | None = None
    api_key_help_url: str | None = None


PROVIDERS: dict[str, ProviderConfig] = {
    "notion": ProviderConfig(
        id="notion",
        name="Notion",
        auth_type="oauth2",
        oauth_authorize_url="https://api.notion.com/v1/oauth/authorize",
        oauth_token_url="https://api.notion.com/v1/oauth/token",
        scopes=["read_content", "read_user_info"],
    ),
    "github": ProviderConfig(
        id="github",
        name="GitHub",
        auth_type="oauth2",
        oauth_authorize_url="https://github.com/login/oauth/authorize",
        oauth_token_url="https://github.com/login/oauth/access_token",
        scopes=["repo", "read:org"],
    ),
    "vercel": ProviderConfig(
        id="vercel",
        name="Vercel",
        auth_type="oauth2",
        oauth_authorize_url="https://vercel.com/oauth/authorize",
        oauth_token_url="https://api.vercel.com/login/oauth/token",
        scopes=["read:projects", "read:deployments"],
    ),
    "airtable": ProviderConfig(
        id="airtable",
        name="Airtable",
        auth_type="oauth2",
        oauth_authorize_url="https://airtable.com/oauth2/v1/authorize",
        oauth_token_url="https://airtable.com/oauth2/v1/token",
        scopes=["data.records:read", "schema.bases:read"],
    ),
    "posthog": ProviderConfig(
        id="posthog",
        name="PostHog",
        auth_type="api_key",
        api_key_fields=["api_key", "project_id", "host"],
        api_key_help_url="https://posthog.com/docs/api",
    ),
    "fireflies": ProviderConfig(
        id="fireflies",
        name="Fireflies",
        auth_type="api_key",
        api_key_fields=["api_key"],
        api_key_help_url="https://fireflies.ai/account/integrations",
    ),
}
