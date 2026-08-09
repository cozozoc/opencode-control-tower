"""Control-room theme tokens shared by every Phase 7 screen."""

from __future__ import annotations

from textual.theme import Theme


CONTROL_TOWER_THEME = Theme(
    name="control-tower",
    primary="#7170ff",
    secondary="#8992a8",
    accent="#8a8f98",
    foreground="#f7f8f8",
    background="#08090a",
    success="#27a644",
    warning="#d7a34b",
    error="#d45967",
    surface="#0f1011",
    panel="#191a1b",
    dark=True,
    variables={
        "block-cursor-text-style": "bold",
        "footer-key-foreground": "#828fff",
        "input-selection-background": "#5e6ad2 55%",
        "border": "#34343a",
        "border-muted": "#23252a",
        "text-muted": "#8a8f98",
    },
)
