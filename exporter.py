# exporter.py
# Export transposed lyrics to Markdown (.md) format.

from __future__ import annotations

import os
import re

from transposer import CHORD_RE, note_to_index, index_to_note


# ── Key detection ─────────────────────────────────────────────────────────────

def detect_new_key(
    text:      str,
    semitones: int,
    use_flats: bool,
    notation:  str,
) -> str | None:
    """
    Scan `text` for the first recognisable chord root and return what that
    root transposes to.  Returns None if no chord is found.
    """
    for line in text.splitlines():
        m = CHORD_RE.search(line)
        if m:
            root = m.group("root")
            acc  = m.group("accidental") or ""
            idx  = note_to_index(root, acc)
            return index_to_note((idx + semitones) % 12, use_flats, notation)
    return None


# ── Filename builder ───────────────────────────────────────────────────────────

def build_filename(
    song_name: str,
    semitones: int,
    new_key:   str | None,
) -> str:
    """
    Construct the suggested export filename.

    Rules (in order):
      1. Key is known → "{song_name} (Key {new_key}).md"
      2. No key but semitones != 0 → "{song_name} (+N semitones).md" / "(-N …)"
      3. No change → "{song_name}.md"
    """
    name = song_name.strip() or "song"

    if new_key:
        return f"{name} (Key {new_key}).md"

    if semitones > 0:
        return f"{name} (+{semitones}).md"
    if semitones < 0:
        return f"{name} ({semitones}).md"

    return f"{name}.md"


# ── Markdown builder ──────────────────────────────────────────────────────────

def build_markdown(
    lines:     list[dict],
    song_name: str,
    semitones: int,
    new_key:   str | None,
    notation:  str,
) -> str:
    """
    Render the list of tokenised lines as a Markdown document.

    Structure:
        # Song Name
        *Transposed …*

        ```
        …lyrics with chords…
        ```
    """
    name = song_name.strip() or "Song"

    # ── Header ───────────────────────────────────────────────────────────────
    header_lines = [f"# {name}", ""]

    if new_key:
        header_lines.append(f"*Transposed to key of **{new_key}***")
    elif semitones != 0:
        sign = "+" if semitones > 0 else ""
        header_lines.append(f"*Transposed {sign}{semitones} semitone{'s' if abs(semitones) != 1 else ''}*")
    else:
        header_lines.append("*Original key*")

    header_lines += ["", "```"]

    # ── Body: reconstruct plain text from token list ──────────────────────────
    body_lines: list[str] = []
    for line_obj in lines:
        tokens = line_obj.get("tokens") or []
        body_lines.append("".join(t["value"] for t in tokens))

    footer = ["```", ""]

    return "\n".join(header_lines + body_lines + footer)


# ── Public API ────────────────────────────────────────────────────────────────

def prepare_export(
    raw_text:  str,
    lines:     list[dict],   # already-transposed token list from transposer
    song_name: str,
    semitones: int,
    use_flats: bool,
    notation:  str,
) -> dict:
    """
    Build the markdown content and suggested filename.

    Returns:
        {
            "ok":       True,
            "content":  "# …\n\n```\n…\n```\n",
            "filename": "imagine (Key D).md",
        }
    """
    try:
        new_key  = detect_new_key(raw_text, semitones, use_flats, notation)
        filename = build_filename(song_name, semitones, new_key)
        content  = build_markdown(lines, song_name, semitones, new_key, notation)
        return {"ok": True, "content": content, "filename": filename}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
