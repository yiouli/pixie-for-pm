from pixie_for_pm.integrations.registry import PROVIDERS


def test_provider_registry_includes_supported_integrations() -> None:
    assert set(PROVIDERS) == {
        "airtable",
        "fireflies",
        "github",
        "notion",
        "posthog",
        "vercel",
    }


def test_provider_registry_describes_api_key_and_oauth_providers() -> None:
    assert PROVIDERS["posthog"].auth_type == "api_key"
    assert PROVIDERS["posthog"].api_key_fields == ["api_key", "project_id", "host"]
    assert PROVIDERS["fireflies"].auth_type == "api_key"
    assert PROVIDERS["fireflies"].api_key_fields == ["api_key"]
    assert PROVIDERS["vercel"].auth_type == "api_key"
    assert PROVIDERS["vercel"].api_key_fields == ["access_token"]
    assert PROVIDERS["vercel"].api_key_help_url == (
        "https://vercel.com/kb/guide/how-do-i-use-a-vercel-api-access-token"
    )

    assert PROVIDERS["github"].auth_type == "oauth2"
    assert PROVIDERS["github"].scopes == ["repo", "read:org"]
    assert PROVIDERS["github"].oauth_authorize_url == "https://github.com/login/oauth/authorize"
    assert PROVIDERS["notion"].oauth_token_url == "https://api.notion.com/v1/oauth/token"
