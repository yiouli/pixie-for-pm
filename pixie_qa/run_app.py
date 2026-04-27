"""Eval Runnable that drives the real Pixie-for-PM application.

The runnable wires the real ``PixieOrchestrator`` against the production
``IntegrationToolsetInitializer`` (Notion + Vercel via hosted MCP) so that
``pixie trace`` exercises live integrations and ``pixie test`` replays the
captured tool I/O via the eval registry. No tool stubs, no fakes.

Note: do NOT add ``from __future__ import annotations`` — it breaks Pydantic
generic resolution for ``pixie.Runnable[DemoScenarioArgs]``.
"""

import logging
import os
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import pixie
from pydantic import BaseModel, Field

from pixie_for_pm.agents.dispatcher import build_dispatcher_handler
from pixie_for_pm.agents.product_designer import build_product_designer_handler
from pixie_for_pm.agents.product_manager import build_product_manager_handler
from pixie_for_pm.agents.user_researcher import build_user_researcher_handler
from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import AgentRole, IncomingDiscordMessage
from pixie_for_pm.integrations.toolset import build_toolset_initializer
from pixie_for_pm.orchestration.runtime import PixieOrchestrator

logger = logging.getLogger(__name__)


# Connected Discord server in the local connection store (see .env).
EVAL_DISCORD_SERVER_ID = "1459772566528069715"


class DemoScenarioArgs(BaseModel):
    user_messages: list[str] = Field(
        description=(
            "Ordered list of user messages to send through the bot, one per "
            "Discord turn. Each message is dispatched as a real Discord-style "
            "trigger and the bot responds before the next message is sent."
        ),
        min_length=1,
    )


async def _noop(_message: str) -> None:
    return None


class AppRunnable(pixie.Runnable[DemoScenarioArgs]):
    """Drives the real Pixie-for-PM bot end-to-end for tracing and evaluation."""

    @classmethod
    def create(cls) -> "AppRunnable":
        return cls()

    async def run(self, args: DemoScenarioArgs) -> None:
        # ``pixie trace``/``pixie test`` may be invoked from any cwd; resolve
        # the project root explicitly so .env / .state paths are correct.
        project_root = _project_root()
        os.chdir(project_root)

        # Load production settings (this also reads .env from cwd).
        settings = load_settings()

        if settings.openai_api_key is None or settings.openai_api_key.strip() == "":
            raise RuntimeError(
                "OPENAI_API_KEY must be set to run the pixie-for-pm eval scenario."
            )
        if settings.credentials_encryption_key is None:
            raise RuntimeError(
                "CREDENTIALS_ENCRYPTION_KEY must be set so the production "
                "IntegrationToolsetInitializer can decrypt connection credentials."
            )

        toolset_initializer = build_toolset_initializer(settings)

        # Use a stable per-run thread so each turn shares LangGraph state.
        thread_id = f"eval-thread-{uuid4().hex}"
        checkpoint_path = project_root / ".state" / f"pixie-eval-{uuid4().hex}.sqlite"
        try:
            async with PixieOrchestrator(
                checkpoint_path=checkpoint_path,
                agent_handlers={
                    AgentRole.DISPATCHER: build_dispatcher_handler(),
                    AgentRole.PRODUCT_MANAGER: build_product_manager_handler(
                        openai_api_key=settings.openai_api_key,
                    ),
                    AgentRole.USER_RESEARCHER: build_user_researcher_handler(
                        openai_api_key=settings.openai_api_key,
                    ),
                    AgentRole.PRODUCT_DESIGNER: build_product_designer_handler(
                        openai_api_key=settings.openai_api_key,
                    ),
                },
                toolset_initializer=toolset_initializer,
            ) as orchestrator:
                await _run_turns(
                    orchestrator,
                    user_messages=args.user_messages,
                    thread_id=thread_id,
                )
        finally:
            for suffix in ("", "-shm", "-wal"):
                path = checkpoint_path.with_name(checkpoint_path.name + suffix)
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        logger.exception("Failed to clean up eval checkpoint %s", path)


async def _run_turns(
    orchestrator: PixieOrchestrator,
    *,
    user_messages: Sequence[str],
    thread_id: str,
) -> None:
    base_message_id = 1000
    for turn_index, content in enumerate(user_messages, start=1):
        is_first_turn = turn_index == 1
        await orchestrator.dispatch(
            build_dispatch_request(
                IncomingDiscordMessage(
                    discord_message_id=base_message_id + turn_index,
                    discord_server_id=EVAL_DISCORD_SERVER_ID,
                    channel_id=501,
                    thread_id=thread_id,
                    author_id=9001,
                    content=content,
                    directly_mentions_bot=is_first_turn,
                    is_reply_to_bot=not is_first_turn,
                )
            ),
            status_emitter=_noop,
            response_emitter=_noop,
        )


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent
