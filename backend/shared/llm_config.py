"""LLM tier resolver — bridges settings.yaml routing rules and the provider registry.

Code paths:
  - resolve_call(task, workspace_preset, ...) → (provider, tier, params)
  - get_generation_params(task) → GenerationParams

The provider registry is consulted to pick a healthy provider. Tier names
(strong/medium/weak) are the platform-wide vocabulary.
"""

from __future__ import annotations

from typing import Literal

from shared import settings as settings_module
from shared.llm_providers import GenerationParams, LLMProvider, get_registry
from shared.llm_providers.base import TierName

TaskName = str  # e.g. "text_to_query"
WorkspacePreset = Literal["cost_sensitive", "balanced", "quality_first"]


def get_generation_params(task: TaskName) -> GenerationParams:
    s = settings_module.get("llm.generation", {}) or {}
    if task in s:
        return GenerationParams(**s[task])
    if "default" in s:
        return GenerationParams(**s["default"])
    return GenerationParams()


def resolve_tier(
    task: TaskName,
    workspace_preset: WorkspacePreset | str | None = None,
) -> TierName:
    task_defaults = settings_module.get("llm.task_defaults", {}) or {}
    if task not in task_defaults:
        raise KeyError(f"Unknown task: {task!r}. Add it to settings.yaml llm.task_defaults.")

    if workspace_preset:
        presets = settings_module.get("llm.workspace_presets", {}) or {}
        preset = presets.get(workspace_preset, {})
        if task in preset:
            return preset[task]

    return task_defaults[task]


def resolve_tier_with_escalation(
    task: TaskName,
    workspace_preset: WorkspacePreset | str | None = None,
    *,
    previous_failures: int = 0,
    is_complex_multi_cube: bool = False,
) -> TierName:
    base = resolve_tier(task, workspace_preset)
    rules = (settings_module.get("llm.escalation", {}) or {}).get(task, {})
    if previous_failures >= 1 and "on_previous_failure" in rules:
        return rules["on_previous_failure"]
    if is_complex_multi_cube and "on_complex_multi_cube" in rules:
        return rules["on_complex_multi_cube"]
    return base


def resolve_call(
    task: TaskName,
    workspace_preset: WorkspacePreset | str | None = None,
    *,
    previous_failures: int = 0,
    is_complex_multi_cube: bool = False,
    preferred_provider: str | None = None,
) -> tuple[LLMProvider, TierName, GenerationParams]:
    """One-stop resolver. Returns (provider, tier, generation_params).

    Call sites use the returned provider's stream() method:

        provider, tier, params = resolve_call("text_to_query", workspace_preset="balanced")
        async for ev in provider.stream(tier=tier, ..., params=params):
            ...
    """
    tier = resolve_tier_with_escalation(
        task,
        workspace_preset,
        previous_failures=previous_failures,
        is_complex_multi_cube=is_complex_multi_cube,
    )
    provider = get_registry().resolve_provider(preferred=preferred_provider)
    params = get_generation_params(task)
    return provider, tier, params
