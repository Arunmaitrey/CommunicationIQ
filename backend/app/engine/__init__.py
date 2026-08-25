"""Assessment engine: contracts, provider resolution, scoring pipeline.

Nothing in this package scores anything directly. It defines what a capability
must do (``contracts``), decides which implementation does it (``registry``),
and — from M1 — orchestrates them into an attempt score (``pipeline``).
"""
from app.engine.registry import Providers, clear_provider_cache

__all__ = ["Providers", "clear_provider_cache"]
