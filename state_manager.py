# state_manager.py
# Persist lightweight UI state (last folder, etc.) for LocalChords.

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".localchords"
_STATE_FILE = _CONFIG_DIR / "ui_state.json"

_DEFAULTS: dict = {
    "last_folder":  "",
    "chord_color":  "#f9c74f",
    "zoom":         100,
    "font":         "'JetBrains Mono', monospace",
}


def load_state() -> dict:
    """Return persisted state merged with defaults."""
    try:
        if _STATE_FILE.exists():
            saved = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **saved}
    except Exception:
        pass
    return dict(_DEFAULTS)


def save_state(updates: dict) -> dict:
    """Merge *updates* into persisted state and write to disk."""
    try:
        merged = {**load_state(), **updates}
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
