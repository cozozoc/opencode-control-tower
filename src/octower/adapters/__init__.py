"""Runtime adapters that map external APIs into the Phase 2/3 core (§7)."""

from .native_opencode import NativeOpenCodeAdapter

__all__ = ["NativeOpenCodeAdapter"]
