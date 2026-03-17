"""
Translation provider factory.
Selects RAGProvider (Claude+RAG) → ClaudeProvider (Claude only) → LocalProvider (rule-based).
"""

from __future__ import annotations
import logging
from typing import Any, Dict

from config import TranslationConfig, StationConfig

log = logging.getLogger(__name__)


def get_provider(api_key: str, config: TranslationConfig):
    """Return the best available advisory provider."""
    if api_key:
        from src.translation.rag_provider import RAGProvider
        return RAGProvider(api_key=api_key, config=config)
    else:
        log.warning("No Claude API key — using rule-based advisory provider")
        from src.translation.local_provider import LocalProvider
        return LocalProvider()


async def generate_advisory(
    provider,
    forecast: Dict[str, Any],
    station: StationConfig,
) -> Dict[str, Any]:
    """Unified dispatch that handles both async RAGProvider and sync LocalProvider."""
    import inspect
    try:
        method = getattr(provider, "generate_advisory", None)
        if method is None:
            raise AttributeError("provider has no generate_advisory method")

        result = method(forecast, station)

        # Await if the method is a coroutine function (async def)
        if inspect.isawaitable(result):
            result = await result

        return result

    except Exception as exc:
        log.warning(
            "Advisory provider error (%s): %s | cause: %s — trying Claude-direct fallback",
            type(exc).__name__, exc, exc.__cause__,
        )
        # Level 2: Claude without RAG (no FAISS / no HF datasets needed)
        api_key = getattr(provider, "api_key", None)
        config   = getattr(provider, "config",  None)
        if api_key and config:
            try:
                from src.translation.claude_provider import ClaudeProvider
                result2 = ClaudeProvider(api_key=api_key, config=config).generate_advisory(forecast, station)
                log.info("Claude-direct fallback succeeded for %s", station.station_id)
                return result2
            except Exception as exc2:
                log.warning(
                    "Claude-direct fallback also failed (%s): %s | cause: %s — falling back to rule-based",
                    type(exc2).__name__, exc2, exc2.__cause__,
                )
        else:
            log.warning("No api_key on provider — skipping Claude-direct fallback")
        # Level 3: rule-based, zero API cost
        from src.translation.local_provider import LocalProvider
        return LocalProvider().generate_advisory(forecast, station)
