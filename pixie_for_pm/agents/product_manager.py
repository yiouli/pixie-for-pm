from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import pixie
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from pixie_for_pm.agents.deep_agent import DEFAULT_DEEP_AGENT_MODEL, run_deep_agent
from pixie_for_pm.agents.demo_flow import (
    BLOCKED_STATUS,
    OPTIONS_SUMMARY_STAGE,
    PRD_BRIEF_STAGE,
    PRD_READY_STAGE,
    RESEARCH_BRIEF_STAGE,
    RESEARCH_FINDINGS_STAGE,
    parse_demo_handoff,
    serialize_demo_handoff,
)
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentHandoff,
    AgentRole,
    WorkflowContext,
)

DEFAULT_PRODUCT_MANAGER_MODEL = DEFAULT_DEEP_AGENT_MODEL
PRODUCT_MANAGER_AGENT_NAME = "pixie_product_manager"

PRODUCT_MANAGER_SYSTEM_PROMPT = """
You are Pixie's product manager agent.

Respond like a senior PM working inside a cross-functional product team.
Be concrete, concise, and execution-oriented.
Use any connected tools when they materially improve the answer.
When you reference prior internal context, synthesize it instead of repeating it verbatim.
Your scope is JTBD analysis plus drafting mission, vision, and PRD artifacts.
Do not decide which specialist should work next and do not speak directly to the user.
Return artifacts for the coordinator to present.

When the work requires a PRD, write a Lenny Rachitsky-style PRD.
Spell the structure out explicitly with:
- title and one-sentence product thesis
- problem statement
- why now
- target user and core job to be done
- key insights and evidence
- goals and non-goals
- hypotheses
- solution overview
- MVP scope
- user experience notes
- success metrics
- launch and iteration plan
- risks and open questions

For the retention-next-step demo workflow:
- when the coordinator passes research findings, synthesize exactly three
    distinct hypotheses with a high-level proposal for each
- when the coordinator passes a selected option, draft the PRD internally
- if the coordinator passes mission or vision work, return a concrete artifact
    instead of a conversational reply
""".strip()

_NUMBERED_BLOCK_PATTERN = re.compile(r"(?ms)^\s*(\d+)\.\s*(.+?)(?=^\s*\d+\.|\Z)")
_MARKDOWN_CHARS_PATTERN = re.compile(r"[*_`#]")
_URL_PATTERN = re.compile(r"https?://\S+")


def build_product_manager_handler(
    *,
    model: str | BaseChatModel = DEFAULT_PRODUCT_MANAGER_MODEL,
    openai_api_key: str | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        demo_payload = parse_demo_handoff(context.handoff_context)
        if demo_payload is not None:
            if demo_payload.stage == RESEARCH_FINDINGS_STAGE:
                return await _respond_to_research_findings(
                    context,
                    findings=demo_payload.artifact,
                    status=demo_payload.status,
                    model=model,
                    openai_api_key=openai_api_key,
                )
            if demo_payload.stage == PRD_BRIEF_STAGE:
                deep_dive_option = _parse_prd_brief_option(demo_payload.artifact)
                prd = await run_deep_agent(
                    role=AgentRole.PRODUCT_MANAGER,
                    agent_name=PRODUCT_MANAGER_AGENT_NAME,
                    system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
                    context=_without_response_stream(context),
                    model=model,
                    openai_api_key=openai_api_key,
                    execution_context_builder=lambda current_context: _build_prd_context(
                        current_context,
                        option_number=deep_dive_option,
                    ),
                )
                notion_persist = await _persist_prd_artifact(
                    context,
                    option_number=deep_dive_option,
                    prd=prd,
                )
                pixie.wrap(
                    prd,
                    purpose="state",
                    name="prd_artifact",
                    description=(
                        "PRD drafted internally by the PM before asking the user "
                        "whether to spin up a prototype."
                    ),
                )
                persisted, page_url = notion_persist
                reply = _build_prd_reply(
                    persisted=persisted,
                    page_url=page_url,
                    option_number=deep_dive_option,
                )
                return AgentExecution(
                    messages=[],
                    handoffs=[
                        AgentHandoff(
                            source_agent=AgentRole.PRODUCT_MANAGER,
                            target_agent=AgentRole.COORDINATOR,
                            reason=serialize_demo_handoff(
                                stage=PRD_READY_STAGE,
                                artifact=reply,
                            ),
                        )
                    ],
                )

        if demo_payload is not None and demo_payload.stage == RESEARCH_BRIEF_STAGE:
            return AgentExecution(
                messages=[],
                handoffs=[
                    AgentHandoff(
                        source_agent=AgentRole.PRODUCT_MANAGER,
                        target_agent=AgentRole.COORDINATOR,
                        reason=demo_payload.artifact,
                    )
                ],
            )

        content = await run_deep_agent(
            role=AgentRole.PRODUCT_MANAGER,
            agent_name=PRODUCT_MANAGER_AGENT_NAME,
            system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
            context=context,
            model=model,
            openai_api_key=openai_api_key,
            execution_context_builder=_build_default_execution_context,
        )
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.PRODUCT_MANAGER,
                    target_agent=AgentRole.COORDINATOR,
                    reason=content,
                )
            ],
        )

    return _handler


async def _respond_to_research_findings(
    context: WorkflowContext,
    *,
    findings: str,
    status: str,
    model: str | BaseChatModel,
    openai_api_key: str | None,
) -> AgentExecution:
    if status == BLOCKED_STATUS:
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.PRODUCT_MANAGER,
                    target_agent=AgentRole.COORDINATOR,
                    reason=findings,
                )
            ],
        )

    content = await run_deep_agent(
        role=AgentRole.PRODUCT_MANAGER,
        agent_name=PRODUCT_MANAGER_AGENT_NAME,
        system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
        context=context,
        model=model,
        openai_api_key=openai_api_key,
        execution_context_builder=lambda current_context: _build_hypothesis_context(
            current_context,
            findings=findings,
        ),
    )
    content = _compact_hypothesis_reply(content)
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.COORDINATOR,
                reason=serialize_demo_handoff(
                    stage=OPTIONS_SUMMARY_STAGE,
                    artifact=content,
                ),
            )
        ],
    )


async def _respond_to_prototype_summary(
    context: WorkflowContext,
    *,
    summary: str,
    status: str,
    model: str | BaseChatModel,
    openai_api_key: str | None,
) -> AgentExecution:
    del context, model, openai_api_key
    if status == BLOCKED_STATUS:
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.PRODUCT_MANAGER,
                    target_agent=AgentRole.COORDINATOR,
                    reason=summary,
                )
            ],
        )

    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.COORDINATOR,
                reason=_build_prototype_review_reply(summary),
            )
        ],
    )


def _build_default_execution_context(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Execution context:",
            "- Work like the PM lead for a cross-functional product squad.",
            "- Use connected tools when they materially improve confidence or speed.",
            "Connected integrations:",
            _describe_integrations(context),
        )
    )


def _parse_prd_brief_option(brief: str) -> int:
    match = re.search(r"Selected option:\s*#?(\d+)", brief)
    if match is None:
        return 1
    return int(match.group(1))


def _build_research_brief(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Retention demo brief:",
            f"- User request: {context.user_message}",
            (
                "- Identify why retention is low, what repeat-use barrier matters "
                "most, and what behavior change seems most promising."
            ),
            (
                "- Return the smallest defensible synthesis the PM can use "
                "to propose three next-build hypotheses."
            ),
        )
    )


def _build_research_handoff_message(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Here's how I'm thinking about this:",
            (
                "Before I recommend what to build next, I want to confirm where "
                "retention is breaking, which repeat-use barrier matters most, "
                "and what behavior change is most likely to move the metric."
            ),
            "",
            "Planned steps:",
            "1. Ask the user researcher to pull the strongest existing evidence and patterns.",
            "2. Synthesize the biggest retention barrier and the most promising leverage points.",
            "3. Come back with three hypotheses and a recommendation on which one to deepen.",
        )
    )


def _build_hypothesis_context(context: WorkflowContext, *, findings: str) -> str:
    return "\n".join(
        (
            _build_default_execution_context(context),
            "Retention demo instructions:",
            "- The user researcher already completed the insight pass.",
            "- Use the research findings below to propose exactly three hypotheses.",
            (
                "- For each hypothesis, include the idea, why it should "
                "improve retention, and a high-level proposal."
            ),
            (
                "- Keep the full user-facing reply concise: three numbered items "
                "plus one closing question, with no long intro or memo sections."
            ),
            (
                "- Use this format exactly: `1. <option> - Idea: ... Why: ... "
                "Proposal: ...` and repeat for options 2 and 3."
            ),
            "- End by asking the user which option to deepen next.",
            "Research findings:",
            findings,
        )
    )


def _build_prd_context(context: WorkflowContext, *, option_number: int) -> str:
    return "\n".join(
        (
            _build_default_execution_context(context),
            "Retention demo instructions:",
            (
                f"- The user asked to go deeper on option #{option_number} "
                "from the prior PM response."
            ),
            (
                "- Draft the PRD internally using the Lenny Rachitsky-style "
                "structure from the system prompt."
            ),
            (
                "- Return only the internal PRD body. Do not mention Notion, "
                "tool calls, Vercel, publication, or what you completed."
            ),
            (
                "- Use these exact section headings: Title and one-sentence "
                "product thesis; Problem statement; Why now; Target user and core "
                "job to be done; Key insights and evidence; Goals and non-goals; "
                "Hypotheses; Solution overview; MVP scope; User experience notes; "
                "Success metrics; Launch and iteration plan; Risks and open questions."
            ),
            (
                "- Be specific enough that a product designer can turn it "
                "into a clickable Vercel prototype."
            ),
            "- Do not ask the user follow-up questions in this artifact.",
        )
    )


def _build_prototype_review_context(context: WorkflowContext, *, summary: str) -> str:
    return "\n".join(
        (
            _build_default_execution_context(context),
            "Retention demo instructions:",
            "- The designer has already translated the PRD into a clickable prototype.",
            "- Summarize the PRD and prototype together for the user.",
            (
                "- Call out what was designed, what behavior change it targets, "
                "and what feedback you want from the user before delivery."
            ),
            "Designer handback:",
            summary,
        )
    )


_NOTION_PAGE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?notion\.(?:so|site)/[^\s)>\]]+",
    re.IGNORECASE,
)


async def _persist_prd_artifact(
    context: WorkflowContext,
    *,
    option_number: int,
    prd: str,
) -> tuple[bool, str | None]:
    """Save the PRD to Notion. Returns (persisted, url) where url may be None."""
    title = f"Retention Demo PRD - Option #{option_number}"
    create_tool = _find_tool_by_fragments(
        context,
        required=("notion",),
        any_of=("create-pages", "create_pages"),
    )
    if create_tool is not None:
        result = await _safe_invoke(
            create_tool,
            {
                "pages": [
                    {
                        "properties": {"title": title},
                        "content": prd,
                    }
                ]
            },
        )
        if result is not None:
            return True, _extract_notion_url(result)

    update_tool = _find_tool_by_fragments(
        context,
        required=("notion",),
        any_of=("update-page", "update_page", "update_content"),
    )
    if update_tool is not None:
        result = await _safe_invoke(
            update_tool,
            {
                "page_title": title,
                "content_updates": prd,
            },
        )
        if result is not None:
            return True, _extract_notion_url(result)

    return False, None


def _extract_recent_pm_reply(context: WorkflowContext) -> str | None:
    for message in reversed(context.transcript):
        if message.agent == AgentRole.PRODUCT_MANAGER and message.content.strip():
            return message.content
    return None


def _build_prd_reply(
    *, persisted: bool, page_url: str | None, option_number: int
) -> str:
    if page_url is not None:
        prd_line = f"PRD for option #{option_number} ready: {page_url}"
    elif persisted:
        prd_line = (
            f"PRD for option #{option_number} saved to Notion (page link not returned)."
        )
    else:
        prd_line = f"PRD for option #{option_number} drafted internally (Notion write was not available)."
    return f"{prd_line}\nWant me to spin up a quick clickable prototype for it next?"


def _build_designer_brief_from_history(
    context: WorkflowContext,
    recent_pm_reply: str | None,
) -> str:
    """Assemble a brief for the designer from the prior PM reply and any URL."""
    notion_url: str | None = None
    if recent_pm_reply is not None:
        match = _NOTION_PAGE_URL_PATTERN.search(recent_pm_reply)
        if match is not None:
            notion_url = match.group(0)

    lines = ["The user approved building a clickable prototype based on the PRD."]
    if notion_url is not None:
        lines.append(f"PRD source: {notion_url}")
        lines.append(
            "Fetch the PRD from this Notion URL with the Notion tool, then translate "
            "it into a clickable Vercel prototype."
        )
    else:
        lines.append(
            "Use the prior PM message in this conversation as the PRD reference."
        )

    if recent_pm_reply is not None:
        lines.append("")
        lines.append("Prior PM message:")
        lines.append(recent_pm_reply.strip())

    # Surface user request for additional context.
    lines.append("")
    lines.append(f"User context: {context.user_message.strip()}")
    return "\n".join(lines)


def _find_tool_by_fragments(
    context: WorkflowContext,
    *,
    required: tuple[str, ...],
    any_of: tuple[str, ...],
) -> BaseTool | None:
    for tool in context.toolset.tools:
        name = tool.name.casefold()
        if not all(fragment in name for fragment in required):
            continue
        if any(fragment in name for fragment in any_of):
            return tool
    return None


async def _safe_invoke(tool: BaseTool, payload: dict[str, object]) -> str | None:
    try:
        result = await tool.ainvoke(payload)
    except Exception:  # noqa: BLE001 - integration boundary
        return None
    if isinstance(result, tuple):
        result = result[0]
    if result is None:
        return None
    return str(result)


def _extract_notion_url(result: str | None) -> str | None:
    if result is None:
        return None
    match = _NOTION_PAGE_URL_PATTERN.search(result)
    if match is None:
        return None
    return match.group(0)


def _compact_hypothesis_reply(content: str) -> str:
    blocks = _NUMBERED_BLOCK_PATTERN.findall(content)
    if len(blocks) < 3:
        return content

    lines: list[str] = []
    for number, block in blocks[:3]:
        option_text = _compact_option_block(block)
        lines.append(f"{number}. {option_text}")
    lines.append("Which option should I deepen next: #1, #2, or #3?")
    return "\n".join(lines)


def _compact_option_block(block: str) -> str:
    lines = [_clean_line(line) for line in block.splitlines()]
    lines = [
        line
        for line in lines
        if line
        and "which option" not in line.casefold()
        and "which direction" not in line.casefold()
    ]
    if not lines:
        return _truncate_words(block, 28)

    title, inline_body = _split_option_title(lines[0])
    body = " ".join(part for part in (inline_body, *lines[1:]) if part)
    idea = _extract_labeled_fragment(body, (r"Idea",)) or _first_sentence(body)
    why = _extract_labeled_fragment(body, (r"Why(?: it should improve retention)?",))
    proposal = (
        _extract_labeled_fragment(body, (r"High-level proposal", r"Proposal")) or idea
    )

    return " ".join(
        fragment
        for fragment in (
            title,
            f"Idea: {_truncate_words(idea, 8)}." if idea else None,
            f"Why: {_truncate_words(why, 6)}." if why else None,
            f"Proposal: {_truncate_words(proposal, 8)}." if proposal else None,
        )
        if fragment
    )


def _build_prototype_review_reply(summary: str) -> str:
    url = _extract_url(summary)
    prototype_summary = _extract_prefixed_line(summary, "Prototype summary:")
    if prototype_summary is None:
        prototype_summary = "The concept turns the selected retention idea into a lighter weekly prep loop."

    lines = []
    if url is not None:
        lines.append(
            f"I went deeper on that option and there is a clickable prototype ready: {url}"
        )
    else:
        lines.append("I went deeper on that option and the prototype draft is ready.")
    lines.append(_truncate_words(prototype_summary, 24))
    lines.append("Tell me what you want to change before we move it into delivery.")
    return "\n".join(lines)


def _split_option_title(line: str) -> tuple[str, str]:
    match = re.search(r"\s+-\s+Idea:", line)
    if match is None:
        return line.rstrip(".:"), ""
    return line[: match.start()].rstrip(".:- "), line[match.start() + 3 :].strip()


def _extract_labeled_fragment(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(labels)
    all_labels = (
        r"Idea|Why(?: it should improve retention)?|High-level proposal|Proposal"
    )
    match = re.search(
        rf"(?:{label_pattern}):\s*(.+?)(?=(?:{all_labels}):|$)",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return match.group(1).strip()


def _extract_prefixed_line(text: str, prefix: str) -> str | None:
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if line.lower().startswith(prefix.lower()):
            return line[len(prefix) :].strip()
    return None


def _extract_url(text: str) -> str | None:
    match = _URL_PATTERN.search(text)
    if match is None:
        return None
    return match.group(0)


def _first_sentence(text: str) -> str:
    cleaned = _clean_line(text)
    if cleaned == "":
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", cleaned)
    if match is not None:
        return match.group(1).strip()
    return cleaned


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]).rstrip(".,;:") + "..."


def _clean_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = cleaned.lstrip("-* ").strip()
    cleaned = _MARKDOWN_CHARS_PATTERN.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _find_tool(context: WorkflowContext, tool_name: str) -> BaseTool | None:
    for tool in context.toolset.tools:
        if tool.name == tool_name:
            return tool
    return None


async def _invoke_text_tool(
    context: WorkflowContext,
    tool_name: str,
    payload: dict[str, object],
) -> str | None:
    tool = _find_tool(context, tool_name)
    if tool is None:
        return None

    result = await tool.ainvoke(payload)
    if isinstance(result, tuple):
        return str(result[0])
    return str(result)


def _describe_integrations(context: WorkflowContext) -> str:
    integrations = [
        (
            f"- {integration.provider_name} ({integration.provider_id}): "
            f"tools={', '.join(integration.tool_names) or 'none'}"
        )
        for integration in context.toolset.integrations
    ]
    if not integrations:
        return "- No connected integrations were detected."
    return "\n".join(integrations)


def _without_response_stream(context: WorkflowContext) -> WorkflowContext:
    return WorkflowContext(
        thread_key=context.thread_key,
        current_agent=context.current_agent,
        user_message=context.user_message,
        transcript=context.transcript,
        trigger=context.trigger,
        toolset=context.toolset,
        status_emitter=context.status_emitter,
        response_emitter=None,
        public_message_emitter=context.public_message_emitter,
        handoff_context=context.handoff_context,
    )


__all__ = [
    "DEFAULT_PRODUCT_MANAGER_MODEL",
    "PRODUCT_MANAGER_AGENT_NAME",
    "PRODUCT_MANAGER_SYSTEM_PROMPT",
    "build_product_manager_handler",
]
