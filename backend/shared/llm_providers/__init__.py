"""Multi-provider LLM client.

The platform routes LLM calls through provider-agnostic tiers (strong / medium / weak).
Each provider (Bedrock, Anthropic, Alibaba, Mock) implements a common interface
defined in `base.py` and is registered in `registry.py`.

Public entry points:

    from shared.llm_providers import get_registry, ProviderUnavailable
    registry = get_registry()
    provider = registry.resolve(tier_name)        # returns a healthy provider
    async for ev in provider.stream(...):
        ...

Application code never references model_id strings directly. Routing always goes
through `shared.llm_config.resolve_call(...)`.
"""

from .base import (
    GenerationParams,
    LLMProvider,
    ProviderHealth,
    ProviderUnavailable,
    StreamEvent,
    TokenUsage,
)
from .registry import ProviderRegistry, get_registry

__all__ = [
    "GenerationParams",
    "LLMProvider",
    "ProviderHealth",
    "ProviderRegistry",
    "ProviderUnavailable",
    "StreamEvent",
    "TokenUsage",
    "get_registry",
]
