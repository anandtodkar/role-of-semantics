"""Semantic grounding benchmark for LLM agents in industrial automation.

Companion artefact for the survey paper *The Role of Semantics and Contextualised
Data in Enhancing AI Results: A Survey of Semantic Technologies in Industrial
Automation and Their Usability for LLMs and AI Agents*.

The package is deliberately dependency-light and fully deterministic: every
number reported in the paper can be regenerated with ``python run_experiments.py``
without network access, API keys, or GPUs.
"""

__version__ = "1.0.0"

__all__ = [
    "vocab",
    "units",
    "statemachine",
    "plant",
    "kg",
    "shapes",
    "conditions",
    "tasks",
    "retrieval",
    "validation",
    "toolgen",
    "metrics",
    "llm",
    "experiments",
    "report",
]
