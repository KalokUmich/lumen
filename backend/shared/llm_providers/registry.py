"""Provider registry — lifecycle + health check + tier resolution.

Loaded once at startup. Each enabled provider's health_check() runs concurrently;
failed providers are marked unavailable for the lifetime of the process.

Use:

    from shared.llm_providers import get_registry
    registry = get_registry()
    await registry.startup()                           # in service lifespan
    provider = registry.resolve_provider(tier="medium")
    ...
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog

from shared import settings as settings_module

from .alibaba import AlibabaProvider
from .anthropic import AnthropicProvider
from .base import LLMProvider, ProviderHealth, ProviderUnavailable, TierName
from .bedrock import BedrockProvider
from .mock import MockProvider

logger = structlog.get_logger(__name__)


_PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "bedrock": BedrockProvider,
    "anthropic": AnthropicProvider,
    "alibaba": AlibabaProvider,
    "mock": MockProvider,
}


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._default_provider: str | None = None
        self._fallback_chain: list[str] = []
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    async def startup(self) -> None:
        """Construct enabled providers; run health checks; cache results."""
        if self._started:
            return

        # Mock-only short-circuit for local smoke tests.
        if os.environ.get("USE_MOCK_LLM", "").lower() in ("1", "true", "yes"):
            mock = MockProvider()
            self._providers["mock"] = mock
            self._health["mock"] = await mock.health_check()
            self._default_provider = "mock"
            self._fallback_chain = []
            self._started = True
            logger.info("provider_registry_started", mode="mock_only")
            return

        s = settings_module.settings()
        sec = settings_module.secrets()
        llm_settings = s.get("llm", {})
        llm_secrets = sec.get("llm", {})

        providers_cfg = llm_settings.get("providers", {})
        self._default_provider = llm_settings.get("default_provider")
        self._fallback_chain = list(llm_settings.get("fallback_providers", []) or [])

        # Construct each enabled provider.
        instances: dict[str, LLMProvider] = {}
        for name, cfg in providers_cfg.items():
            if not cfg.get("enabled"):
                logger.info("provider_disabled", name=name)
                continue
            cls = _PROVIDER_CLASSES.get(name)
            if cls is None:
                logger.warning("provider_unknown", name=name)
                continue
            try:
                instance = cls(config=cfg, secrets=llm_secrets.get(name, {}))
                instances[name] = instance
            except Exception as e:
                self._health[name] = ProviderHealth(
                    name=name,
                    healthy=False,
                    error=f"construction_failed: {type(e).__name__}: {e}",
                )
                logger.warning("provider_construction_failed", name=name, error=str(e))

        # Run health checks concurrently.
        async def _check(name: str, p: LLMProvider) -> tuple[str, ProviderHealth]:
            return name, await p.health_check()

        if instances:
            results = await asyncio.gather(
                *[_check(n, p) for n, p in instances.items()], return_exceptions=False
            )
            for name, health in results:
                self._health[name] = health
                if health.healthy:
                    self._providers[name] = instances[name]
                    logger.info(
                        "provider_healthy",
                        name=name,
                        latency_ms=round(health.latency_ms or 0, 1),
                    )
                else:
                    logger.warning("provider_unhealthy", name=name, error=health.error)

        self._started = True
        logger.info(
            "provider_registry_started",
            healthy=list(self._providers.keys()),
            default=self._default_provider,
            fallbacks=self._fallback_chain,
        )

    def health_report(self) -> dict[str, Any]:
        return {
            "default": self._default_provider,
            "fallbacks": self._fallback_chain,
            "providers": {
                name: {
                    "healthy": h.healthy,
                    "error": h.error,
                    "latency_ms": round(h.latency_ms or 0, 1) if h.latency_ms else None,
                    "checked_at": h.checked_at,
                }
                for name, h in self._health.items()
            },
        }

    def resolve_provider(
        self,
        *,
        preferred: str | None = None,
    ) -> LLMProvider:
        """Pick a healthy provider. Try preferred → default → fallbacks → any healthy."""
        chain: list[str] = []
        if preferred:
            chain.append(preferred)
        if self._default_provider and self._default_provider not in chain:
            chain.append(self._default_provider)
        for fb in self._fallback_chain:
            if fb not in chain:
                chain.append(fb)
        # Last resort: anything healthy.
        for name in self._providers:
            if name not in chain:
                chain.append(name)

        for name in chain:
            if name in self._providers:
                return self._providers[name]

        raise ProviderUnavailable(
            f"No healthy LLM provider available. Tried: {chain}. "
            f"Health: {self.health_report()['providers']}"
        )

    def is_available(self, provider_name: str) -> bool:
        return provider_name in self._providers


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def reset_registry() -> None:
    """Used in tests."""
    global _registry
    _registry = None
