# file_explorer.py
# Local file system browsing and favorites management for LocalChords.

from __future__ import annotations

import json
import os
from pathlib import Path

SUPPORTED_EXTS = frozenset({
    '.txt', '.md',
    '.pdf', '.docx', '.rtf',
    '.cho', '.chopro',
    '.lnk', '.url',
})

_CONFIG_DIR = Path.home() / ".localchords"
_FAVS_FILE  = _CONFIG_DIR / "favorites.json"


# ── Directory listing ─────────────────────────────────────────────────────────

def list_directory(path: str) -> dict:
    """
    List all supported files in *path*.

    Returns:
        {"ok": True,  "path": str, "entries": [...]  }
        {"ok": False, "error": str}

    Each entry:
        {"name", "stem", "path", "ext", "modified", "size", "is_favorite"}
    """
    try:
        p = Path(path)
        if not p.is_dir():
            return {"ok": False, "error": f"Not a directory: '{path}'"}

        favs = {f["path"] for f in _load_favs_raw()}
        entries: list[dict] = []

        for item in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if not item.is_file():
                continue
            if item.suffix.lower() not in SUPPORTED_EXTS:
                continue
            try:
                stat = item.stat()
                entries.append({
                    "name":        item.name,
                    "stem":        item.stem,
                    "path":        str(item),
                    "ext":         item.suffix.lower(),
                    "modified":    stat.st_mtime,
                    "size":        stat.st_size,
                    "is_favorite": str(item) in favs,
                })
            except OSError:
                continue

        return {"ok": True, "path": str(p), "entries": entries}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Favorites ─────────────────────────────────────────────────────────────────

def get_favorites() -> dict:
    """Return all favorites whose files still exist on disk."""
    favs = [f for f in _load_favs_raw() if os.path.isfile(f.get("path", ""))]
    return {"ok": True, "favorites": favs}


def toggle_favorite(path: str) -> dict:
    """Add or remove *path* from favorites."""
    favs  = _load_favs_raw()
    paths = {f["path"] for f in favs}

    if path in paths:
        favs        = [f for f in favs if f["path"] != path]
        is_favorite = False
    else:
        item = Path(path)
        try:
            stat = item.stat()
            favs.append({
                "name":     item.name,
                "stem":     item.stem,
                "path":     path,
                "ext":      item.suffix.lower(),
                "modified": stat.st_mtime,
            })
            is_favorite = True
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    _save_favs(favs)
    return {
        "ok":          True,
        "is_favorite": is_favorite,
        "favorites":   favs,
    }


# ── Internal ──────────────────────────────────────────────────────────────────

def _load_favs_raw() -> list[dict]:
    try:
        if _FAVS_FILE.exists():
            return json.loads(_FAVS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_favs(favs: list[dict]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _FAVS_FILE.write_text(
        json.dumps(favs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
