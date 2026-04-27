from __future__ import annotations

import json
import re
from dataclasses import dataclass

RETENTION_NEXT_STEP_DEMO_WORKFLOW = "retention_next_step_demo"
_DEEP_DIVE_PATTERN = re.compile(r"\bgo\s+deeper\s+on\s+#?(\d+)\b", re.IGNORECASE)

RESEARCH_BRIEF_STAGE = "research_brief"
RESEARCH_FINDINGS_STAGE = "research_findings"
PROTOTYPE_BRIEF_STAGE = "prototype_brief"
PROTOTYPE_SUMMARY_STAGE = "prototype_summary"

READY_STATUS = "ready"
BLOCKED_STATUS = "blocked"


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
    "BLOCKED_STATUS",
    "DemoHandoffPayload",
    "PROTOTYPE_BRIEF_STAGE",
    "PROTOTYPE_SUMMARY_STAGE",
    "READY_STATUS",
    "RESEARCH_BRIEF_STAGE",
    "RESEARCH_FINDINGS_STAGE",
    "RETENTION_NEXT_STEP_DEMO_WORKFLOW",
    "is_retention_next_step_demo",
    "parse_deep_dive_option",
    "parse_demo_handoff",
    "serialize_demo_handoff",
]
