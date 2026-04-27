from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from langchain_core.tools import BaseTool

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.integrations.toolset import (
    DiscordTriggerContext,
    build_toolset_initializer,
)
from pixie_for_pm.integrations.vercel import get_vercel_credentials
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.store import build_connection_store

LIVE_SERVER_ID = "1459772566528069715"
_ENABLE_ENV = "PIXIE_RUN_LIVE_VERCEL_MCP_E2E"
_VERCEL_URL_PATTERN = re.compile(r"https?://[^\s)\]>]*vercel\.app[^\s)\]>]*")


def _require_live_run() -> None:
    if os.environ.get(_ENABLE_ENV) != "1":
        pytest.skip(
            f"Set {_ENABLE_ENV}=1 to run the live Vercel MCP e2e against server "
            f"{LIVE_SERVER_ID}."
        )


def _write_test_nextjs_app(root: Path, *, package_name: str) -> dict[str, str]:
    (root / "pages").mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": package_name,
                "private": True,
                "version": "0.0.1",
                "scripts": {
                    "dev": "next dev",
                    "build": "next build",
                    "start": "next start",
                },
                "dependencies": {
                    "next": "16.2.4",
                    "react": "19.2.5",
                    "react-dom": "19.2.5",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "pages" / "index.js").write_text(
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
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and "vercel.app" in url:
            return url.rstrip("\"'")
        alias = value.get("alias")
        if isinstance(alias, list):
            for candidate in alias:
                if isinstance(candidate, str) and "vercel.app" in candidate:
                    return candidate.rstrip("\"'")
    match = _VERCEL_URL_PATTERN.search(_stringify_result(value))
    if match is None:
        return None
    return match.group(0).rstrip("\"'")


def _find_tool(toolset: tuple[BaseTool, ...], name: str) -> BaseTool:
    for tool in toolset:
        if tool.name == name:
            return tool
    raise AssertionError(f"Missing tool {name}")


def _extract_deployment_id(value: object) -> str | None:
    if isinstance(value, dict):
        deployment_id = value.get("id")
        if isinstance(deployment_id, str) and deployment_id != "":
            return deployment_id
    return None


async def _wait_for_ready_deployment(
    *,
    deployment_id: str,
    discord_server_id: str,
) -> tuple[dict[str, object] | None, str | None]:
    settings = load_settings()
    encryption_key = settings.credentials_encryption_key
    if encryption_key is None or encryption_key.strip() == "":
        return (
            None,
            "Missing CREDENTIALS_ENCRYPTION_KEY for authenticated readiness check.",
        )

    credentials = await get_vercel_credentials(
        discord_server_id,
        store=build_connection_store(settings),
        cipher=CredentialCipher(encryption_key),
    )
    if credentials is None:
        return (
            None,
            "Missing stored Vercel credentials for authenticated readiness check.",
        )

    access_token = credentials.get("access_token")
    if access_token is None or access_token.strip() == "":
        return None, "Stored Vercel credentials do not include an access_token."

    last_observation: str | None = None
    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(12):
            try:
                response = await client.get(
                    f"https://api.vercel.com/v13/deployments/{deployment_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    last_observation = (
                        f"attempt={attempt + 1}; unexpected_payload={payload}"
                    )
                else:
                    ready_state = payload.get("readyState")
                    status = payload.get("status")
                    if ready_state == "READY" or status == "READY":
                        return payload, None
                    if payload.get("errorCode") is not None:
                        return payload, (
                            f"attempt={attempt + 1}; status={status}; "
                            f"ready_state={ready_state}; error={payload.get('errorCode')}"
                        )
                    last_observation = (
                        f"attempt={attempt + 1}; status={status}; "
                        f"ready_state={ready_state}; public={payload.get('public')}"
                    )
            except httpx.HTTPError as exc:
                last_observation = f"attempt={attempt + 1}; error={exc}"
            await asyncio.sleep(5)
    return None, last_observation


@pytest.mark.asyncio
async def test_live_vercel_mcp_can_create_and_deploy_nextjs_project(
    tmp_path: Path,
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
    assert "vercel_list_projects" in vercel_tool_names, vercel_tool_names
    assert "vercel_create_project" in vercel_tool_names, vercel_tool_names
    assert "vercel_create_deployment" in vercel_tool_names, vercel_tool_names

    issues: list[str] = []

    list_projects_tool = _find_tool(toolset.tools, "vercel_list_projects")
    try:
        projects_result = await list_projects_tool.ainvoke({})
        if not isinstance(projects_result, list):
            issues.append(
                "vercel_list_projects returned an unexpected payload. "
                f"result={projects_result}"
            )
    except Exception as exc:  # noqa: BLE001 - live integration boundary
        issues.append(
            "vercel_list_projects failed for the live Vercel connection. "
            f"available_tools={vercel_tool_names}; error={exc}"
        )

    project_name = f"pixie-vercel-live-e2e-{uuid4().hex[:8]}"
    app_root = tmp_path / project_name
    deployment_files = _write_test_nextjs_app(app_root, package_name=project_name)

    create_project_tool = _find_tool(toolset.tools, "vercel_create_project")
    try:
        create_result = await create_project_tool.ainvoke(
            {"name": project_name, "framework": "nextjs"}
        )
        if (
            not isinstance(create_result, dict)
            or create_result.get("name") != project_name
        ):
            issues.append(
                "vercel_create_project returned an unexpected payload. "
                f"project_name={project_name}; result={create_result}"
            )
    except Exception as exc:  # noqa: BLE001 - live integration boundary
        issues.append(
            "vercel_create_project raised before returning a project record. "
            f"project_name={project_name}; error={exc}"
        )

    deploy_tool = _find_tool(toolset.tools, "vercel_create_deployment")
    deploy_result: object | None = None
    try:
        deploy_result = await deploy_tool.ainvoke(
            {"project_name": project_name, "files": deployment_files}
        )
    except Exception as exc:  # noqa: BLE001 - live integration boundary
        issues.append(
            "vercel_create_deployment raised before returning a deployment result. "
            f"project_name={project_name}; error={exc}"
        )

    deployment_url = _extract_vercel_url(deploy_result)
    if deployment_url is None:
        issues.append(
            "Expected vercel_create_deployment to return a live .vercel.app URL for "
            "the disposable Next.js app, but it did not. "
            f"project_name={project_name}; result={_stringify_result(deploy_result)}"
        )
    else:
        deployment_id = _extract_deployment_id(deploy_result)
        if deployment_id is None:
            issues.append(
                "Expected vercel_create_deployment to return a deployment id, but it did not. "
                f"project_name={project_name}; result={_stringify_result(deploy_result)}"
            )
        else:
            ready_deployment, verification_error = await _wait_for_ready_deployment(
                deployment_id=deployment_id,
                discord_server_id=LIVE_SERVER_ID,
            )
            if verification_error is not None:
                issues.append(
                    "Deployment did not reach READY through the authenticated Vercel API. "
                    f"project_name={project_name}; deployment_id={deployment_id}; "
                    f"url={deployment_url}; observation={verification_error}"
                )
            elif ready_deployment is not None:
                project = ready_deployment.get("project")
                if not isinstance(project, dict):
                    issues.append(
                        "Authenticated deployment lookup returned no project metadata. "
                        f"project_name={project_name}; deployment_id={deployment_id}; "
                        f"payload={ready_deployment}"
                    )
                else:
                    if project.get("name") != project_name:
                        issues.append(
                            "Authenticated deployment lookup returned the wrong project name. "
                            f"expected={project_name}; actual={project.get('name')}"
                        )
                    if project.get("framework") != "nextjs":
                        issues.append(
                            "Authenticated deployment lookup did not preserve the "
                            "Next.js framework. "
                            f"project_name={project_name}; "
                            f"actual_framework={project.get('framework')}"
                        )
                if ready_deployment.get("public") is not True:
                    issues.append(
                        "Authenticated deployment lookup did not mark the deployment public. "
                        f"project_name={project_name}; deployment_id={deployment_id}; "
                        f"payload={ready_deployment}"
                    )

    assert not issues, "\n\n".join(issues)
