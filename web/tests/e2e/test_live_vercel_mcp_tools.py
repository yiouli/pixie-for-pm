from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.integrations.toolset import (
    DiscordTriggerContext,
    build_toolset_initializer,
)

LIVE_SERVER_ID = "1459772566528069715"
_ENABLE_ENV = "PIXIE_RUN_LIVE_VERCEL_MCP_E2E"
_VERCEL_URL_PATTERN = re.compile(r"https?://[^\s)\]>]*vercel\.app[^\s)\]>]*")


def _require_live_run() -> None:
    if os.environ.get(_ENABLE_ENV) != "1":
        pytest.skip(
            f"Set {_ENABLE_ENV}=1 to run the live Vercel MCP e2e against server "
            f"{LIVE_SERVER_ID}."
        )


def _write_test_nextjs_app(root: Path) -> None:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "pixie-vercel-live-e2e",
                "private": True,
                "version": "0.0.1",
                "scripts": {
                    "dev": "next dev",
                    "build": "next build",
                    "start": "next start",
                },
                "dependencies": {
                    "next": "15.3.1",
                    "react": "19.1.0",
                    "react-dom": "19.1.0",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "next.config.ts").write_text(
        'import type { NextConfig } from "next";\n\n'
        "const nextConfig: NextConfig = {};\n\n"
        "export default nextConfig;\n",
        encoding="utf-8",
    )
    (root / "app" / "page.tsx").write_text(
        "export default function Home() {\n"
        "  return (\n"
        "    <main>\n"
        "      <h1>Pixie Vercel MCP Live E2E</h1>\n"
        "      <p>Verifies direct Vercel MCP deployment without LLM involvement.</p>\n"
        "    </main>\n"
        "  );\n"
        "}\n",
        encoding="utf-8",
    )


def _stringify_result(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_stringify_result(item) for item in value)
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        return json.dumps(value, sort_keys=True)
    return str(value)


def _extract_vercel_url(value: object) -> str | None:
    match = _VERCEL_URL_PATTERN.search(_stringify_result(value))
    if match is None:
        return None
    return match.group(0)


def _extract_first_team_id(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                team_id = item.get("id")
                if isinstance(team_id, str) and team_id != "":
                    return team_id
    if isinstance(value, dict):
        for nested in value.values():
            team_id = _extract_first_team_id(nested)
            if team_id is not None:
                return team_id
    return None


def _find_tool(toolset: tuple[BaseTool, ...], name: str) -> BaseTool:
    for tool in toolset:
        if tool.name == name:
            return tool
    raise AssertionError(f"Missing tool {name}")


@pytest.mark.asyncio
async def test_live_vercel_mcp_can_create_and_deploy_nextjs_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_live_run()

    settings = load_settings()
    settings = replace(
        settings,
        connection_store_sqlite_path=settings.connection_store_sqlite_path.resolve(),
        langgraph_checkpoint_path=settings.langgraph_checkpoint_path.resolve(),
    )
    initializer = build_toolset_initializer(settings)
    trigger = DiscordTriggerContext(
        discord_server_id=LIVE_SERVER_ID,
        discord_user_id="live-vercel-e2e",
        channel_id=1459772566528069715,
        thread_id="live-vercel-mcp-e2e",
        message_id=1,
        thread_key="live-vercel-mcp-e2e",
        dispatch_reason="manual_e2e",
    )

    toolset = await initializer.initialize(trigger)
    failures = {failure.provider_id: failure.error for failure in toolset.failures}
    assert "vercel" not in failures, failures

    vercel_tool_names = [
        tool.name for tool in toolset.tools if tool.name.startswith("vercel_")
    ]
    assert "vercel_list_teams" in vercel_tool_names, vercel_tool_names
    assert "vercel_list_projects" in vercel_tool_names, vercel_tool_names
    assert "vercel_deploy_to_vercel" in vercel_tool_names, vercel_tool_names

    issues: list[str] = []

    list_teams_tool = _find_tool(toolset.tools, "vercel_list_teams")
    teams_result: object | None = None
    try:
        teams_result = await list_teams_tool.ainvoke({})
    except Exception as exc:  # noqa: BLE001 - live integration boundary
        issues.append(
            "vercel_list_teams failed for the live MCP connection. "
            f"available_tools={vercel_tool_names}; error={exc}"
        )

    team_id = _extract_first_team_id(teams_result)
    if team_id is None:
        issues.append(f"Could not discover a Vercel team id from result={teams_result}")

    if team_id is not None:
        list_projects_tool = _find_tool(toolset.tools, "vercel_list_projects")
        try:
            projects_result = await list_projects_tool.ainvoke({"teamId": team_id})
            if projects_result is None:
                issues.append(
                    f"vercel_list_projects returned no data for discovered team_id={team_id}"
                )
        except Exception as exc:  # noqa: BLE001 - live integration boundary
            issues.append(
                "vercel_list_projects failed for the discovered team id. "
                f"team_id={team_id}; error={exc}"
            )

    app_root = tmp_path / "live-vercel-mcp-nextjs"
    _write_test_nextjs_app(app_root)

    deploy_tool = _find_tool(toolset.tools, "vercel_deploy_to_vercel")
    monkeypatch.chdir(app_root)
    deploy_result: object | None = None
    try:
        deploy_result = await deploy_tool.ainvoke({})
    except Exception as exc:  # noqa: BLE001 - live integration boundary
        issues.append(
            "vercel_deploy_to_vercel raised before returning a deployment result. "
            f"cwd={app_root}; error={exc}"
        )

    deployment_url = _extract_vercel_url(deploy_result)
    if deployment_url is None:
        issues.append(
            "Expected vercel_deploy_to_vercel to return a live .vercel.app URL for "
            "the disposable Next.js app, but it did not. "
            f"cwd={app_root}; result={_stringify_result(deploy_result)}"
        )

    assert not issues, "\n\n".join(issues)
