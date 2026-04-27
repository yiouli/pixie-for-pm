"""Evaluators for the retention demo eval.

These check user-observable behaviour against the real production transcript:

- Did the PM save the PRD to Notion via a real write tool (not just paste it)?
- Did the visible Discord reply include a Notion link to that artifact?
- Did the workflow actually hand off to the product designer?
- Did the designer publish a Vercel deployment with a real URL?
- Did the PM surface that Vercel URL in a Discord reply?
- Did the PM avoid dumping long spec/PRD bodies into Discord?

All checks are mechanical — they read the wrapped outputs/state captured by
``pixie_for_pm/orchestration/runtime.py`` and ``pixie_for_pm/integrations/toolset.py``.
"""

from __future__ import annotations

import re
from typing import Any

from pixie.eval.evaluable import Evaluable
from pixie.eval.evaluation import Evaluation

# ────────────────────────── helpers ──────────────────────────


def _outputs_named(evaluable: Evaluable, prefix: str) -> list[Any]:
    return [item for item in evaluable.eval_output if item.name.startswith(prefix)]


def _public_replies(evaluable: Evaluable) -> list[tuple[str, str]]:
    """Return [(wrap_name, reply_text), ...] in turn order."""
    items: list[tuple[int, str, str]] = []
    for item in _outputs_named(evaluable, "public_reply_"):
        try:
            turn_id = int(item.name.rsplit("_", 1)[-1])
        except ValueError:
            turn_id = 0
        if isinstance(item.value, str):
            items.append((turn_id, item.name, item.value))
    items.sort(key=lambda x: x[0])
    return [(name, text) for _, name, text in items]


def _all_handoffs(evaluable: Evaluable) -> list[dict[str, Any]]:
    handoffs: list[dict[str, Any]] = []
    for item in _outputs_named(evaluable, "handoff_sequence_"):
        if isinstance(item.value, list):
            handoffs.extend(h for h in item.value if isinstance(h, dict))
    return handoffs


def _tool_args(evaluable: Evaluable) -> list[dict[str, Any]]:
    """Return all captured ``{tool, args}`` records, ordered by turn."""
    records: list[dict[str, Any]] = []
    for item in _outputs_named(evaluable, "tool_args__"):
        if isinstance(item.value, dict):
            records.append(item.value)
    return records


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


_NOTION_LINK = re.compile(
    r"https?://(?:www\.)?notion\.(?:so|site)/[^\s)>\]]+", re.IGNORECASE
)
_VERCEL_LINK = re.compile(r"https?://[^\s)>\]]*vercel\.app[^\s)>\]]*", re.IGNORECASE)


# Substrings that identify real Notion *write* tool names. The hosted MCP
# exposes write capability under different names depending on workspace; we
# accept any of these.
_NOTION_WRITE_TOOL_FRAGMENTS = (
    "create-page",
    "create_page",
    "update-page",
    "update_page",
    "append-block",
    "append_block",
    "patch-block",
    "patch_block",
    "create-blocks",
    "create_blocks",
    "update_content",
    "update-content",
)


def _is_notion_write(tool_name: str) -> bool:
    lower = tool_name.lower()
    if "notion" not in lower:
        return False
    return any(fragment in lower for fragment in _NOTION_WRITE_TOOL_FRAGMENTS)


def _is_vercel_deploy(tool_name: str) -> bool:
    lower = tool_name.lower()
    return "vercel" in lower and "deploy" in lower


# ────────────────────────── evaluators ──────────────────────────


_PRD_BODY_MARKERS = (
    "prd",
    "product requirements",
    "## mvp",
    "## solution overview",
    "## goals",
    "## recommendation",
    "problem statement",
    "success metrics",
    "launch and iteration plan",
    "risks and open questions",
)


def _extract_write_body(args: dict[str, Any]) -> str:
    """Pull out the most likely body text from a Notion write tool call."""
    candidates: list[str] = []
    for key in (
        "new_str",
        "content",
        "content_updates",
        "page_title",
        "title",
        "body",
    ):
        value = args.get(key)
        if isinstance(value, str):
            candidates.append(value)
    pages = args.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            for key in ("content", "body"):
                value = page.get(key)
                if isinstance(value, str):
                    candidates.append(value)
            properties = page.get("properties")
            if isinstance(properties, dict):
                title = properties.get("title")
                if isinstance(title, str):
                    candidates.append(title)
    return "\n".join(candidates)


def notion_write_with_substantive_body(evaluable: Evaluable) -> Evaluation:
    """The PM must persist the PRD to Notion via a real write tool, with body.

    A pass requires both:
      1. A real Notion write tool was invoked (create/update/append-page-style).
      2. The write body looks PRD-like — at least 80 words AND contains a
         PRD/product-spec marker (e.g. "PRD", "Problem statement", "MVP").

    This guards against false positives where unrelated Notion writes (research
    scratch pages, comments, etc.) are counted as a saved PRD.
    """
    write_calls = [
        record
        for record in _tool_args(evaluable)
        if isinstance(record.get("tool"), str) and _is_notion_write(record["tool"])
    ]
    if not write_calls:
        observed = sorted(
            {
                tool
                for r in _tool_args(evaluable)
                if isinstance((tool := r.get("tool")), str)
            }
        )
        return Evaluation(
            score=0.0,
            reasoning=(
                "No Notion write tool was invoked. The PM should save the PRD to "
                f"Notion instead of pasting it into Discord. Tools observed: {observed}."
            ),
        )

    qualifying: list[str] = []
    for record in write_calls:
        args = record.get("args") or {}
        if not isinstance(args, dict):
            continue
        body = _extract_write_body(args)
        body_lower = body.lower()
        if _word_count(body) < 80:
            continue
        if not any(marker in body_lower for marker in _PRD_BODY_MARKERS):
            continue
        tool_name = record.get("tool")
        if isinstance(tool_name, str):
            qualifying.append(tool_name)

    if not qualifying:
        return Evaluation(
            score=0.0,
            reasoning=(
                f"Saw {len(write_calls)} Notion write call(s) but none looked like a "
                "PRD save: body must be ≥80 words and contain a PRD/product-spec "
                "marker (PRD, Problem statement, MVP, Goals, Solution overview, etc.)."
            ),
        )

    return Evaluation(
        score=1.0,
        reasoning=f"Observed PRD-like Notion write call(s) via {qualifying}.",
    )


def notion_link_surfaced_in_reply(evaluable: Evaluable) -> Evaluation:
    """After the Notion write, at least one public reply must include a Notion URL."""
    replies = _public_replies(evaluable)
    if not replies:
        return Evaluation(score=0.0, reasoning="No public replies captured.")

    linked = [name for name, text in replies if _NOTION_LINK.search(text)]
    if not linked:
        return Evaluation(
            score=0.0,
            reasoning=(
                "No public reply contained a Notion link. The PM should reply with a "
                "link to the saved Notion artifact instead of pasting the body."
            ),
        )
    return Evaluation(
        score=1.0,
        reasoning=f"Notion link surfaced in {linked}.",
    )


def designer_handoff_occurred(evaluable: Evaluable) -> Evaluation:
    """The workflow must hand off to the product designer at some point."""
    handoffs = _all_handoffs(evaluable)
    pairs = [
        (h.get("source_agent"), h.get("target_agent"))
        for h in handoffs
        if isinstance(h.get("source_agent"), str)
        and isinstance(h.get("target_agent"), str)
    ]
    if any(target == "product_designer" for _, target in pairs):
        return Evaluation(
            score=1.0,
            reasoning=f"Saw a handoff to product_designer in {pairs}.",
        )
    return Evaluation(
        score=0.0,
        reasoning=(
            "No handoff to product_designer occurred. The PM should hand off after "
            f"the user approves prototyping. Handoffs observed: {pairs}."
        ),
    )


def vercel_deployment_published(evaluable: Evaluable) -> Evaluation:
    """A Vercel deployment tool must have been called."""
    calls = [
        record
        for record in _tool_args(evaluable)
        if isinstance(record.get("tool"), str) and _is_vercel_deploy(record["tool"])
    ]
    if calls:
        return Evaluation(
            score=1.0,
            reasoning=f"Observed {len(calls)} Vercel deploy call(s).",
        )
    return Evaluation(
        score=0.0,
        reasoning=(
            "No Vercel deployment tool was called. The product designer should "
            "publish a clickable prototype to Vercel."
        ),
    )


def vercel_link_surfaced_in_reply(evaluable: Evaluable) -> Evaluation:
    """A final public reply must include the Vercel deployment URL."""
    replies = _public_replies(evaluable)
    if not replies:
        return Evaluation(score=0.0, reasoning="No public replies captured.")

    linked = [name for name, text in replies if _VERCEL_LINK.search(text)]
    if not linked:
        return Evaluation(
            score=0.0,
            reasoning=(
                "No public reply contained a Vercel URL. The coordinator should surface the "
                "deployed prototype link to the user."
            ),
        )
    return Evaluation(
        score=1.0,
        reasoning=f"Vercel URL surfaced in {linked}.",
    )


def no_long_message_dump(evaluable: Evaluable) -> Evaluation:
    """No public reply may dump a long body — limit ~120 words per message."""
    limit = 120
    replies = _public_replies(evaluable)
    if not replies:
        return Evaluation(score=0.0, reasoning="No public replies captured.")

    over_limit = [
        (name, _word_count(text)) for name, text in replies if _word_count(text) > limit
    ]
    if over_limit:
        details = ", ".join(f"{name}={count}w" for name, count in over_limit)
        return Evaluation(
            score=0.0,
            reasoning=(
                f"The following replies exceed {limit} words and dump long content "
                f"into Discord instead of saving to Notion + linking: {details}."
            ),
        )
    return Evaluation(
        score=1.0,
        reasoning=f"All {len(replies)} public replies are within {limit} words.",
    )


def conversation_has_three_distinct_turns(evaluable: Evaluable) -> Evaluation:
    """The bot should produce three distinct conversational turns:

    1. Coordinator presents 3 options after the research and PM passes complete.
    2. Coordinator asks if the user wants a prototype after the PRD step.
    3. Coordinator returns a third public reply after the designer step.

    Link-specific checks are covered separately by:
    - notion_link_surfaced_in_reply
    - vercel_link_surfaced_in_reply
    """
    replies = _public_replies(evaluable)
    if len(replies) < 3:
        return Evaluation(
            score=0.0,
            reasoning=(
                f"Expected at least 3 public turns, got {len(replies)}: "
                f"{[name for name, _ in replies]}."
            ),
        )

    first = replies[0][1]
    if not re.search(r"(?m)^\s*[123][\.\)]\s", first):
        return Evaluation(
            score=0.0,
            reasoning=(
                f"First turn ({replies[0][0]}) did not present numbered options."
            ),
        )

    second_text = replies[1][1]
    second_lower = second_text.lower()
    prototype_markers = (
        "prototype",
        "spin up",
        "want me to",
        "should i build",
        "build a",
    )
    if not any(marker in second_lower for marker in prototype_markers):
        return Evaluation(
            score=0.0,
            reasoning=(
                f"Second turn ({replies[1][0]}) did not ask the user about spinning up a prototype."
            ),
        )

    third_text = replies[2][1]
    if third_text.strip() == "":
        return Evaluation(
            score=0.0,
            reasoning=(f"Third turn ({replies[2][0]}) was empty."),
        )

    return Evaluation(
        score=1.0,
        reasoning="Three-turn shape matched: options → prototype ask → final reply.",
    )
