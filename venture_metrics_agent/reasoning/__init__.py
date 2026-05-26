"""reasoning-style research controller for Venture Metrics.

This package keeps the experimental reasoning-first architecture separate from
the existing linear retrieval agent so both paths can be compared.
"""

from venture_metrics_agent.reasoning.controller import ReasoningOptions, answer_question_reasoning

__all__ = ["ReasoningOptions", "answer_question_reasoning"]
