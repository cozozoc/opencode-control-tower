"""Console-only TUI lifecycle for the headless start command."""

from __future__ import annotations


class TuiNop:
    """Acknowledge reattachment without owning an interactive TUI process."""

    async def reattach(self, root_id: str) -> bool:
        print(f"[octower] Backend restored; attach remains available for {root_id}")
        return True
