"""Structured workspace for reasoning-style runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReasoningStep:
    step: int
    phase: str
    decision: str
    reason: str
    tool: str | None = None
    observation: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "phase": self.phase,
            "decision": self.decision,
            "reason": self.reason,
            "tool": self.tool,
            "observation": self.observation,
        }


@dataclass
class ResearchWorkspace:
    question: str
    route: dict[str, Any]
    steps: list[ReasoningStep] = field(default_factory=list)

    def add_step(
        self,
        *,
        phase: str,
        decision: str,
        reason: str,
        tool: str | None = None,
        observation: dict[str, Any] | None = None,
    ) -> None:
        self.steps.append(
            ReasoningStep(
                step=len(self.steps) + 1,
                phase=phase,
                decision=decision,
                reason=reason,
                tool=tool,
                observation=observation or {},
            )
        )

    def trace(self) -> list[dict[str, Any]]:
        return [step.as_dict() for step in self.steps]
