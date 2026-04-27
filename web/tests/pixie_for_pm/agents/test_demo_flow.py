"""Unit tests for the demo-flow parsers added for the retention demo."""

from __future__ import annotations

import pytest

from pixie_for_pm.agents.demo_flow import (
    parse_bare_option_choice,
    parse_deep_dive_option,
    parse_prototype_approval,
)

_HYPOTHESES_REPLY = (
    "1. Tighten onboarding\n"
    "2. Add weekly habit loops\n"
    "3. Manager nudges\n"
    "Which option should I deepen next: #1, #2, or #3?"
)
_PROTOTYPE_REPLY = (
    "PRD for option #2 ready: https://www.notion.so/x\n"
    "Want me to spin up a quick clickable prototype for it next?"
)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("2", 2),
        ("#2", 2),
        ("option 2", 2),
        ("Option #3.", 3),
        ("the second one", 2),
        ("third option", 3),
    ],
)
def test_parse_bare_option_choice_matches_when_pm_asked(
    message: str, expected: int
) -> None:
    assert (
        parse_bare_option_choice(message, recent_pm_reply=_HYPOTHESES_REPLY)
        == expected
    )


def test_parse_bare_option_choice_returns_none_without_prompt_marker() -> None:
    # PM never asked which option to deepen → bare "2" should not hijack.
    assert parse_bare_option_choice("2", recent_pm_reply="Anything else?") is None


def test_parse_bare_option_choice_returns_none_when_no_pm_reply() -> None:
    assert parse_bare_option_choice("2", recent_pm_reply=None) is None


def test_parse_deep_dive_option_still_matches_explicit_phrasing() -> None:
    assert parse_deep_dive_option("Go deeper on option #2.") == 2


@pytest.mark.parametrize(
    "message",
    ["sure", "Yes please", "go ahead", "yeah, do it", "OK", "sounds good"],
)
def test_parse_prototype_approval_matches_after_prototype_prompt(message: str) -> None:
    assert parse_prototype_approval(message, recent_pm_reply=_PROTOTYPE_REPLY) is True


def test_parse_prototype_approval_rejects_no_answer() -> None:
    assert (
        parse_prototype_approval("no, scrap it", recent_pm_reply=_PROTOTYPE_REPLY)
        is False
    )


def test_parse_prototype_approval_requires_prompt_marker() -> None:
    assert parse_prototype_approval("sure", recent_pm_reply="Hi") is False


def test_parse_prototype_approval_handles_missing_prior_reply() -> None:
    assert parse_prototype_approval("sure", recent_pm_reply=None) is False
