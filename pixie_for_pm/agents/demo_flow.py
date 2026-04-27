from __future__ import annotations

import json
import re
from dataclasses import dataclass

RETENTION_NEXT_STEP_DEMO_WORKFLOW = "retention_next_step_demo"
_DEEP_DIVE_PATTERN = re.compile(
    r"\bgo\s+deeper\s+on\s+(?:option\s*)?#?(\d+)\b",
    re.IGNORECASE,
)

# Bare option pick like "2", "#2", "option 2", "the second one".
_BARE_NUMBER_PATTERN = re.compile(r"^\s*(?:option\s*)?#?\s*([1-9])\b\s*\.?\s*$")
_ORDINAL_OPTIONS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "1st": 1,
    "2nd": 2,
    "3rd": 3,
    "one": 1,
    "two": 2,
    "three": 3,
}
_OPTION_PROMPT_MARKERS = (
    "which option should i deepen",
    "which option do you want me to deepen",
    "which option should we deepen",
    "which option should i turn into a prd",
    "which one should i turn into a prd",
    "turn into a prd",
    "draft a prd",
)
_PROTOTYPE_PROMPT_MARKERS = (
    "want me to spin up a quick clickable prototype",
    "want me to spin up a prototype",
    "want me to build a prototype",
    "shall i spin up a prototype",
    "should i spin up a prototype",
    "want me to turn that into a quick clickable prototype",
    "want me to make a clickable prototype",
    "want me to make a prototype",
)
_APPROVAL_PATTERN = re.compile(
    r"\b(sure|yes|yep|yeah|yup|ok|okay|please|do it|go ahead|let'?s go|sounds good)\b",
    re.IGNORECASE,
)

RESEARCH_BRIEF_STAGE = "research_brief"
RESEARCH_FINDINGS_STAGE = "research_findings"
OPTIONS_SUMMARY_STAGE = "options_summary"
PRD_BRIEF_STAGE = "prd_brief"
PRD_READY_STAGE = "prd_ready"
PROTOTYPE_BRIEF_STAGE = "prototype_brief"
PROTOTYPE_SUMMARY_STAGE = "prototype_summary"
AWAITING_PROTOTYPE_APPROVAL_STAGE = "awaiting_prototype_approval"

READY_STATUS = "ready"
BLOCKED_STATUS = "blocked"

OPTIONS_SUMMARY_ARTIFACT_KIND = "options_summary"
PRD_READY_ARTIFACT_KIND = "prd_ready"
PROTOTYPE_READY_ARTIFACT_KIND = "prototype_ready"


@dataclass(frozen=True)
class DemoHandoffPayload:
    workflow: str
    stage: str
    status: str
    artifact: str


def is_retention_next_step_demo(message: str) -> bool:
    normalized = _normalize(message)
    if "retention" not in normalized:
        return False

    return any(
        phrase in normalized
        for phrase in (
            "what should we build next",
            "what should we do next",
            "improve that",
            "improve it",
            "improve this",
        )
    )


def parse_deep_dive_option(message: str) -> int | None:
    match = _DEEP_DIVE_PATTERN.search(message)
    if match is None:
        return None
    return int(match.group(1))


def parse_bare_option_choice(
    message: str,
    *,
    recent_pm_reply: str | None,
) -> int | None:
    """Match a bare option pick like "2", "#2", "option 2", "the second one".

    Only fires when the most recent PM reply asked the user which option to deepen.
    This avoids hijacking unrelated numeric replies.
    """
    if recent_pm_reply is None:
        return None
    normalized_recent_reply = recent_pm_reply.casefold()
    if not _contains_any(normalized_recent_reply, _OPTION_PROMPT_MARKERS) and not (
        re.search(r"(?m)^\s*1\.\s+", recent_pm_reply) is not None
        and re.search(r"(?m)^\s*2\.\s+", recent_pm_reply) is not None
    ):
        return None

    text = message.strip().casefold()
    if text == "":
        return None

    bare = _BARE_NUMBER_PATTERN.match(text)
    if bare is not None:
        choice = int(bare.group(1))
        return choice if 1 <= choice <= 9 else None

    # Match "the second one", "second option", "option two", etc.
    for token, value in _ORDINAL_OPTIONS.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            return value
    return None


def parse_prototype_approval(
    message: str,
    *,
    recent_pm_reply: str | None,
) -> bool:
    """Match short approvals after the PM asks about spinning up a prototype."""
    if recent_pm_reply is None:
        return False
    normalized_recent_reply = recent_pm_reply.casefold()
    if not _contains_any(normalized_recent_reply, _PROTOTYPE_PROMPT_MARKERS) and not (
        "prototype" in normalized_recent_reply and "?" in recent_pm_reply
    ):
        return False
    text = message.strip()
    if text == "":
        return False
    if "no" in text.casefold().split():
        return False
    return _APPROVAL_PATTERN.search(text) is not None


def parse_prd_request_option(
    message: str,
    *,
    recent_reply: str | None,
) -> int | None:
    text = message.strip().casefold()
    if text == "":
        return None
    if not any(keyword in text for keyword in ("prd", "mission", "vision")):
        return None

    bare_choice = parse_bare_option_choice(message, recent_pm_reply=recent_reply)
    if bare_choice is not None:
        return bare_choice

    numeric_match = re.search(r"\b(?:option\s*)?#?([1-9])\b", text)
    if numeric_match is not None:
        return int(numeric_match.group(1))

    for token, value in _ORDINAL_OPTIONS.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            return value
    return None


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def serialize_demo_artifact(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def parse_demo_artifact(artifact: str) -> dict[str, object] | None:
    try:
        payload = json.loads(artifact)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def serialize_demo_handoff(
    *,
    stage: str,
    artifact: str,
    status: str = READY_STATUS,
) -> str:
    return json.dumps(
        {
            "workflow": RETENTION_NEXT_STEP_DEMO_WORKFLOW,
            "stage": stage,
            "status": status,
            "artifact": artifact,
        },
        separators=(",", ":"),
    )


def parse_demo_handoff(reason: str | None) -> DemoHandoffPayload | None:
    if reason is None or reason.strip() == "":
        return None

    try:
        payload = json.loads(reason)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    workflow = payload.get("workflow")
    stage_value = payload.get("stage")
    status_value = payload.get("status")
    artifact_value = payload.get("artifact")
    if workflow != RETENTION_NEXT_STEP_DEMO_WORKFLOW:
        return None
    if not isinstance(stage_value, str):
        return None
    if not isinstance(status_value, str):
        return None
    if not isinstance(artifact_value, str):
        return None

    return DemoHandoffPayload(
        workflow=workflow,
        stage=stage_value,
        status=status_value,
        artifact=artifact_value,
    )


def _normalize(message: str) -> str:
    return message.casefold().strip()


__all__ = [
    "AWAITING_PROTOTYPE_APPROVAL_STAGE",
    "BLOCKED_STATUS",
    "DemoHandoffPayload",
    "OPTIONS_SUMMARY_ARTIFACT_KIND",
    "OPTIONS_SUMMARY_STAGE",
    "PRD_READY_ARTIFACT_KIND",
    "PRD_BRIEF_STAGE",
    "PRD_READY_STAGE",
    "PROTOTYPE_READY_ARTIFACT_KIND",
    "PROTOTYPE_BRIEF_STAGE",
    "PROTOTYPE_SUMMARY_STAGE",
    "READY_STATUS",
    "RESEARCH_BRIEF_STAGE",
    "RESEARCH_FINDINGS_STAGE",
    "RETENTION_NEXT_STEP_DEMO_WORKFLOW",
    "is_retention_next_step_demo",
    "parse_bare_option_choice",
    "parse_demo_artifact",
    "parse_deep_dive_option",
    "parse_demo_handoff",
    "parse_prd_request_option",
    "parse_prototype_approval",
    "serialize_demo_artifact",
    "serialize_demo_handoff",
]
