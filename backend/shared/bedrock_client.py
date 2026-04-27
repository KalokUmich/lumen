"""Backwards-compat shim — all real logic moved to shared.llm_providers.

Kept so any older import path doesn't break during the transition. New code
should use:

    from shared.llm_providers import get_registry
    provider = get_registry().resolve_provider()
    async for ev in provider.stream(tier=..., ...):
        ...
"""

from shared.llm_providers import (
    GenerationParams,
    LLMProvider as _LLMProvider,
    StreamEvent,
    TokenUsage,
    get_registry,
)

__all__ = ["GenerationParams", "StreamEvent", "TokenUsage", "BedrockClient"]


class BedrockClient:
    """Compatibility wrapper around the new provider registry.

    Old call sites used:
        BedrockClient.from_env().stream(tier=..., ...)
    The registry handles tier→provider routing now, so this just forwards.
    """

    def __init__(self):
        self._registry = get_registry()

    @classmethod
    def from_env(cls) -> "BedrockClient":
        return cls()

    async def stream(self, *, tier, **kwargs):
        provider = self._registry.resolve_provider()
        # `tier` may be the legacy TierConfig dataclass; extract its name.
        tier_name = getattr(tier, "name", tier)
        async for ev in provider.stream(tier=tier_name, **kwargs):
            yield ev
