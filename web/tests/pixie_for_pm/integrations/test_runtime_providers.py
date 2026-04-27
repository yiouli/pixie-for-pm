from __future__ import annotations

import json
from collections.abc import Mapping

import httpx
import pytest
from langchain_core.tools import StructuredTool

from pixie_for_pm.integrations.runtime_providers import (
    AirtableToolProvider,
    FirefliesToolProvider,
    HostedMcpToolProvider,
    VercelToolProvider,
)
from pixie_for_pm.integrations.toolset import DiscordTriggerContext


def _trigger() -> DiscordTriggerContext:
    return DiscordTriggerContext(
        discord_server_id="guild-123",
        discord_user_id="user-9",
        channel_id=456,
        thread_id="thread-1",
        message_id=789,
        thread_key="thread-1",
        dispatch_reason="direct_bot_mention",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_id", "url", "credentials"),
    [
        (
            "notion",
            "https://mcp.notion.com/mcp",
            {"access_token": "notion-token"},
        ),
        (
            "github",
            "https://api.githubcopilot.com/mcp/",
            {"access_token": "github-token"},
        ),
    ],
)
async def test_hosted_mcp_provider_loads_remote_tools_with_bearer_auth(
    provider_id: str,
    url: str,
    credentials: dict[str, str],
) -> None:
    calls: list[tuple[object | None, dict[str, object]]] = []

    async def _loader(
        session: object | None,
        **kwargs: object,
    ) -> list[StructuredTool]:
        calls.append((session, kwargs))
        return [
            StructuredTool.from_function(
                coroutine=lambda **_: pytest.fail("tool should not be invoked"),
                name="search",
                description="Remote tool",
            )
        ]

    provider = HostedMcpToolProvider(
        provider_id=provider_id,
        server_url=url,
        token_field="access_token",
        tool_loader=_loader,
    )

    tools = await provider.load_tools(credentials=credentials, trigger=_trigger())

    assert [tool.name for tool in tools] == ["search"]
    assert calls == [
        (
            None,
            {
                "connection": {
                    "transport": "streamable_http",
                    "url": url,
                    "headers": {
                        "Authorization": f"Bearer {credentials['access_token']}"
                    },
                },
                "server_name": provider_id,
                "tool_name_prefix": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_hosted_mcp_provider_refreshes_unauthorized_tokens_and_retries() -> None:
    calls: list[dict[str, object]] = []

    async def _loader(
        session: object | None,
        **kwargs: object,
    ) -> list[StructuredTool]:
        del session
        calls.append(kwargs)
        if len(calls) == 1:
            request = httpx.Request("POST", "https://mcp.notion.com/mcp")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError(
                "401 Unauthorized",
                request=request,
                response=response,
            )
        return [
            StructuredTool.from_function(
                coroutine=lambda **_: pytest.fail("tool should not be invoked"),
                name="search",
                description="Remote tool",
            )
        ]

    async def _refresh(
        credentials: Mapping[str, str],
    ) -> tuple[dict[str, str], list[str] | None]:
        assert credentials["refresh_token"] == "notion-refresh-token"
        assert credentials["oauth_client_id"] == "registered-client-id"
        assert credentials["oauth_resource"] == "https://mcp.notion.com"
        return (
            {
                "access_token": "refreshed-notion-token",
                "refresh_token": "next-refresh-token",
            },
            ["read", "write"],
        )

    provider = HostedMcpToolProvider(
        provider_id="notion",
        server_url="https://mcp.notion.com/mcp",
        token_field="access_token",
        tool_loader=_loader,
        token_refresher=_refresh,
    )
    credentials = {
        "access_token": "expired-notion-token",
        "refresh_token": "notion-refresh-token",
        "oauth_client_id": "registered-client-id",
        "oauth_resource": "https://mcp.notion.com",
    }

    tools = await provider.load_tools(credentials=credentials, trigger=_trigger())

    assert [tool.name for tool in tools] == ["search"]
    assert [call["connection"] for call in calls] == [
        {
            "transport": "streamable_http",
            "url": "https://mcp.notion.com/mcp",
            "headers": {"Authorization": "Bearer expired-notion-token"},
        },
        {
            "transport": "streamable_http",
            "url": "https://mcp.notion.com/mcp",
            "headers": {"Authorization": "Bearer refreshed-notion-token"},
        },
    ]
    assert credentials["access_token"] == "refreshed-notion-token"
    assert credentials["refresh_token"] == "next-refresh-token"


@pytest.mark.asyncio
async def test_hosted_mcp_provider_refreshes_wrapped_unauthorized_tokens() -> None:
    calls: list[dict[str, object]] = []

    async def _loader(
        session: object | None,
        **kwargs: object,
    ) -> list[StructuredTool]:
        del session
        calls.append(kwargs)
        if len(calls) == 1:
            request = httpx.Request("POST", "https://mcp.notion.com/mcp")
            response = httpx.Response(401, request=request)
            unauthorized = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=request,
                response=response,
            )
            raise ExceptionGroup("mcp request failed", [unauthorized])
        return [
            StructuredTool.from_function(
                coroutine=lambda **_: pytest.fail("tool should not be invoked"),
                name="search",
                description="Remote tool",
            )
        ]

    async def _refresh(
        credentials: Mapping[str, str],
    ) -> tuple[dict[str, str], list[str] | None]:
        assert credentials["refresh_token"] == "notion-refresh-token"
        return ({"access_token": "refreshed-notion-token"}, ["read"])

    provider = HostedMcpToolProvider(
        provider_id="notion",
        server_url="https://mcp.notion.com/mcp",
        token_field="access_token",
        tool_loader=_loader,
        token_refresher=_refresh,
    )
    credentials = {
        "access_token": "expired-notion-token",
        "refresh_token": "notion-refresh-token",
        "oauth_client_id": "registered-client-id",
        "oauth_resource": "https://mcp.notion.com",
    }

    tools = await provider.load_tools(credentials=credentials, trigger=_trigger())

    assert [tool.name for tool in tools] == ["search"]
    assert [call["connection"] for call in calls] == [
        {
            "transport": "streamable_http",
            "url": "https://mcp.notion.com/mcp",
            "headers": {"Authorization": "Bearer expired-notion-token"},
        },
        {
            "transport": "streamable_http",
            "url": "https://mcp.notion.com/mcp",
            "headers": {"Authorization": "Bearer refreshed-notion-token"},
        },
    ]


@pytest.mark.asyncio
async def test_hosted_mcp_provider_requires_reconnect_for_legacy_unauthorized_tokens() -> (
    None
):
    async def _loader(
        session: object | None,
        **kwargs: object,
    ) -> list[StructuredTool]:
        del session, kwargs
        request = httpx.Request("POST", "https://mcp.notion.com/mcp")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError(
            "401 Unauthorized",
            request=request,
            response=response,
        )

    provider = HostedMcpToolProvider(
        provider_id="notion",
        server_url="https://mcp.notion.com/mcp",
        token_field="access_token",
        tool_loader=_loader,
        token_refresher=lambda credentials: pytest.fail(str(credentials)),
    )

    with pytest.raises(RuntimeError, match="Reconnect Notion"):
        await provider.load_tools(
            credentials={"access_token": "legacy-notion-token"},
            trigger=_trigger(),
        )


@pytest.mark.asyncio
async def test_hosted_posthog_provider_uses_eu_endpoint_when_host_is_eu() -> None:
    calls: list[dict[str, object]] = []

    async def _loader(session: object | None, **kwargs: object) -> list[StructuredTool]:
        del session
        calls.append(kwargs)
        return []

    provider = HostedMcpToolProvider(
        provider_id="posthog",
        server_url="https://mcp.posthog.com/mcp",
        token_field="api_key",
        resolve_url=lambda credentials, _trigger: (
            "https://mcp-eu.posthog.com/mcp"
            if credentials["host"].startswith("https://eu.")
            else "https://mcp.posthog.com/mcp"
        ),
        tool_loader=_loader,
    )

    await provider.load_tools(
        credentials={
            "api_key": "posthog-token",
            "host": "https://eu.posthog.com",
            "project_id": "123",
        },
        trigger=_trigger(),
    )

    assert calls[0]["connection"] == {
        "transport": "streamable_http",
        "url": "https://mcp-eu.posthog.com/mcp",
        "headers": {"Authorization": "Bearer posthog-token"},
    }


@pytest.mark.asyncio
async def test_airtable_provider_uses_live_rest_endpoints() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer airtable-token"
        if request.url.path == "/v0/meta/bases":
            return httpx.Response(
                200,
                json={
                    "bases": [
                        {"id": "app123", "name": "Roadmap", "workspaceId": "ws-1"},
                        {"id": "app456", "name": "Other", "workspaceId": "ws-2"},
                    ]
                },
            )
        if request.url.path == "/v0/app123/Roadmap":
            assert request.url.params["filterByFormula"] == "Status='Open'"
            return httpx.Response(200, json={"records": [{"id": "rec1"}]})
        raise AssertionError(f"unexpected request: {request.url}")

    provider = AirtableToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"access_token": "airtable-token"},
        trigger=_trigger(),
    )

    bases = await tools[0].ainvoke({"workspace_id": "ws-1"})
    records = await tools[1].ainvoke(
        {
            "base_id": "app123",
            "table_name": "Roadmap",
            "formula": "Status='Open'",
        }
    )

    assert bases == [{"id": "app123", "name": "Roadmap", "workspaceId": "ws-1"}]
    assert records == {"records": [{"id": "rec1"}]}


@pytest.mark.asyncio
async def test_fireflies_provider_uses_live_graphql_api() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.fireflies.ai/graphql")
        assert request.headers["Authorization"] == "Bearer fireflies-token"
        body = json.loads(request.content.decode("utf-8"))
        operation_name = body["operationName"]
        if operation_name == "SearchTranscripts":
            assert body["variables"] == {"query": "roadmap"}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "transcripts": [
                            {
                                "id": "tr-1",
                                "title": "Roadmap Review",
                                "transcript_url": "https://ff/1",
                            }
                        ]
                    }
                },
            )
        if operation_name == "GetTranscript":
            assert body["variables"] == {"transcriptId": "tr-1"}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "transcript": {
                            "id": "tr-1",
                            "title": "Roadmap Review",
                            "summary": {"gist": "Decision log"},
                        }
                    }
                },
            )
        raise AssertionError(f"unexpected operation: {operation_name}")

    provider = FirefliesToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"api_key": "fireflies-token"},
        trigger=_trigger(),
    )

    transcript = await tools[0].ainvoke({"transcript_id": "tr-1"})
    results = await tools[1].ainvoke({"query": "roadmap"})

    assert transcript == {
        "id": "tr-1",
        "title": "Roadmap Review",
        "summary": {"gist": "Decision log"},
    }
    assert results == [
        {"id": "tr-1", "title": "Roadmap Review", "transcript_url": "https://ff/1"}
    ]


def _vercel_trigger() -> DiscordTriggerContext:
    return _trigger()


@pytest.mark.asyncio
async def test_vercel_tool_provider_lists_projects_with_bearer_token() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200, json={"projects": [{"name": "pixie-retention-demo"}]}
        )

    provider = VercelToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"access_token": "vercel-token"},
        trigger=_vercel_trigger(),
    )
    list_tool = next(t for t in tools if t.name == "vercel_list_projects")

    result = await list_tool.ainvoke({})

    assert result == [{"name": "pixie-retention-demo"}]
    assert captured["method"] == "GET"
    assert captured["url"] == "https://api.vercel.com/v9/projects"
    assert captured["authorization"] == "Bearer vercel-token"


@pytest.mark.asyncio
async def test_vercel_tool_provider_lists_projects_passes_team_id_query_param() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"projects": []})

    provider = VercelToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"access_token": "vercel-token"},
        trigger=_vercel_trigger(),
    )
    list_tool = next(t for t in tools if t.name == "vercel_list_projects")

    await list_tool.ainvoke({"team_id": "team_42"})

    assert captured["url"] == "https://api.vercel.com/v9/projects?teamId=team_42"


@pytest.mark.asyncio
async def test_vercel_tool_provider_creates_project_via_rest() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"id": "prj_1", "name": "pixie-retention"})

    provider = VercelToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"access_token": "vercel-token"},
        trigger=_vercel_trigger(),
    )
    create_tool = next(t for t in tools if t.name == "vercel_create_project")

    result = await create_tool.ainvoke(
        {"name": "pixie-retention", "framework": "nextjs"}
    )

    assert result == {"id": "prj_1", "name": "pixie-retention"}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.vercel.com/v10/projects"
    assert captured["body"] == {"name": "pixie-retention", "framework": "nextjs"}


@pytest.mark.asyncio
async def test_vercel_tool_provider_create_deployment_uploads_inline_files() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "dpl_1",
                "url": "pixie-retention-demo-eval.vercel.app",
                "alias": ["pixie-retention-demo.vercel.app"],
            },
        )

    provider = VercelToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"access_token": "vercel-token"},
        trigger=_vercel_trigger(),
    )
    deploy_tool = next(t for t in tools if t.name == "vercel_create_deployment")

    result = await deploy_tool.ainvoke(
        {
            "project_name": "pixie-retention-demo",
            "files": {"index.html": "<!doctype html><title>x</title>"},
        }
    )

    assert isinstance(result, dict)
    assert result["url"] == "https://pixie-retention-demo-eval.vercel.app"
    assert result["alias"] == ["https://pixie-retention-demo.vercel.app"]
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.vercel.com/v13/deployments"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["name"] == "pixie-retention-demo"
    assert body["public"] is True
    assert body["target"] == "production"
    assert body["files"] == [
        {"file": "index.html", "data": "<!doctype html><title>x</title>"}
    ]


@pytest.mark.asyncio
async def test_vercel_tool_provider_rejects_deployment_without_files() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Unexpected HTTP request: {request.url}")

    provider = VercelToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"access_token": "vercel-token"},
        trigger=_vercel_trigger(),
    )
    deploy_tool = next(t for t in tools if t.name == "vercel_create_deployment")

    with pytest.raises(RuntimeError, match="at least one file"):
        await deploy_tool.ainvoke({"project_name": "pixie-retention-demo", "files": {}})


@pytest.mark.asyncio
async def test_vercel_tool_provider_translates_http_errors_to_runtime_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, json={"error": {"message": "invalid token"}})

    provider = VercelToolProvider(transport=httpx.MockTransport(_handler))
    tools = await provider.load_tools(
        credentials={"access_token": "bad-token"},
        trigger=_vercel_trigger(),
    )
    list_tool = next(t for t in tools if t.name == "vercel_list_projects")

    with pytest.raises(RuntimeError, match="Vercel request failed"):
        await list_tool.ainvoke({})


@pytest.mark.asyncio
async def test_vercel_tool_provider_requires_access_token_in_credentials() -> None:
    provider = VercelToolProvider()
    tools = await provider.load_tools(
        credentials={"access_token": ""},
        trigger=_vercel_trigger(),
    )
    list_tool = next(t for t in tools if t.name == "vercel_list_projects")

    with pytest.raises(RuntimeError, match="Missing access_token"):
        await list_tool.ainvoke({})
