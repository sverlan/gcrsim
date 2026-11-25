"""The agent skill: the text of ``gcrsim/skill/SKILL.md``, shipped with the package."""

from __future__ import annotations

from importlib import resources


def skill_text() -> str:
    """The text of the agent skill (a ``SKILL.md`` file in the Agent Skills format), as printed by ``gcrsim --print-skill``."""
    return (resources.files("gcrsim") / "skill" / "SKILL.md").read_text(encoding="utf-8")
