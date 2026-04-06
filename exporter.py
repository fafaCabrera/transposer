# exporter.py
# Export transposed lyrics to Markdown (.md), ChordPro (.cho), and PDF formats.

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
    ext:       str = ".md",
) -> str:
    """
    Construct the suggested export filename.

    Rules (in order):
      1. Key is known → "{song_name} (Key {new_key}){ext}"
      2. No key but semitones != 0 → "{song_name} (+N){ext}"
      3. No change → "{song_name}{ext}"
    """
    name = song_name.strip() or "song"

    if new_key:
        return f"{name} (Key {new_key}){ext}"

    if semitones > 0:
        return f"{name} (+{semitones}){ext}"
    if semitones < 0:
        return f"{name} ({semitones}){ext}"

    return f"{name}{ext}"


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
    """
    name = song_name.strip() or "Song"

    header_lines = [f"# {name}", ""]

    if new_key:
        header_lines.append(f"*Transposed to key of **{new_key}***")
    elif semitones != 0:
        sign = "+" if semitones > 0 else ""
        header_lines.append(f"*Transposed {sign}{semitones} semitone{'s' if abs(semitones) != 1 else ''}*")
    else:
        header_lines.append("*Original key*")

    header_lines += ["", "```"]

    body_lines: list[str] = []
    for line_obj in lines:
        tokens = line_obj.get("tokens") or []
        body_lines.append("".join(t["value"] for t in tokens))

    footer = ["```", ""]

    return "\n".join(header_lines + body_lines + footer)


# ── ChordPro builder ──────────────────────────────────────────────────────────

def build_chordpro(
    lines:     list[dict],
    song_name: str,
    new_key:   str | None,
) -> str:
    """
    Render the token list as a ChordPro document.

    Chord-only lines immediately followed by a lyric-only line are merged
    so chords appear inline: [Am]Verse text [G]goes here
    """
    name = song_name.strip() or "Song"
    out: list[str] = []

    out.append(f"{{title: {name}}}")
    if new_key:
        out.append(f"{{key: {new_key}}}")
    out.append("")

    i = 0
    while i < len(lines):
        tokens = lines[i].get("tokens") or []

        has_chord = any(t["type"] == "chord" for t in tokens)
        has_text  = any(t["type"] == "text" and t["value"].strip() for t in tokens)

        if has_chord and not has_text:
            # Pure chord line — try to merge with the next lyric line
            next_obj = lines[i + 1] if i + 1 < len(lines) else None
            if next_obj is not None:
                next_tokens = next_obj.get("tokens") or []
                next_has_chord = any(t["type"] == "chord" for t in next_tokens)
                next_has_text  = any(t["type"] == "text"  and t["value"].strip() for t in next_tokens)

                if next_has_text and not next_has_chord:
                    lyric  = "".join(t["value"] for t in next_tokens)
                    merged = _merge_chord_lyric(tokens, lyric)
                    out.append(merged)
                    i += 2
                    continue

            # No lyric line follows — output as bare chord markers
            out.append(" ".join(f"[{t['value']}]" for t in tokens if t["type"] == "chord"))
        else:
            # Mixed or lyric-only line — inline chord markers
            cp = ""
            for t in tokens:
                if t["type"] == "chord":
                    cp += f"[{t['value']}]"
                else:
                    cp += t["value"]
            out.append(cp)

        i += 1

    return "\n".join(out)


def _merge_chord_lyric(chord_tokens: list[dict], lyric: str) -> str:
    """
    Insert [Chord] markers into a lyric string at the column positions where
    each chord appeared in the chord line above it.
    """
    # Build list of (col, chord_value); fall back to sequential position if col absent
    chords: list[tuple[int, str]] = []
    col = 0
    for t in chord_tokens:
        if t["type"] == "chord":
            chords.append((t.get("col", col), t["value"]))
            col += len(t["value"])
        else:
            col += len(t["value"])

    chords.sort(key=lambda x: x[0])

    # Insert markers right-to-left so earlier positions stay valid
    chars = list(lyric)
    for pos, chord in reversed(chords):
        marker = list(f"[{chord}]")
        if pos >= len(chars):
            chars += [" "] * (pos - len(chars)) + marker
        else:
            chars[pos:pos] = marker

    return "".join(chars)


# ── PDF builder ───────────────────────────────────────────────────────────────

def build_pdf(
    lines:          list[dict],
    song_name:      str,
    semitones:      int,
    new_key:        str | None,
    chord_color:    str = "#f9a825",
) -> bytes:
    """
    Render the transposed song as a PDF using fpdf2.

    Chords are rendered in `chord_color`; lyrics in black.
    Returns the PDF as bytes.

    Raises ImportError if fpdf2 is not installed.
    """
    from fpdf import FPDF  # type: ignore

    r, g, b = _hex_to_rgb(chord_color)
    name    = song_name.strip() or "Song"

    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # ── Title ────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, name, new_x="LMARGIN", new_y="NEXT")

    if new_key:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, f"Key of {new_key}", new_x="LMARGIN", new_y="NEXT")
    elif semitones != 0:
        sign = "+" if semitones > 0 else ""
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, f"Transposed {sign}{semitones} semitones", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # ── Body ─────────────────────────────────────────────────────────────────
    pdf.set_font("Courier", size=10)

    for line_obj in lines:
        tokens = line_obj.get("tokens") or []

        if not tokens:
            pdf.ln(5)
            continue

        for token in tokens:
            if token["type"] == "chord":
                pdf.set_text_color(r, g, b)
                pdf.set_font("Courier", "B", 10)
                pdf.write(5, token["value"])
            else:
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Courier", size=10)
                pdf.write(5, token["value"])

        pdf.ln(5)

    pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output())


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert "#rrggbb" to (r, g, b) integers."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (249, 168, 37)   # amber fallback
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ── Public API ────────────────────────────────────────────────────────────────

def prepare_export(
    raw_text:  str,
    lines:     list[dict],
    song_name: str,
    semitones: int,
    use_flats: bool,
    notation:  str,
) -> dict:
    """Build Markdown content + suggested filename."""
    try:
        new_key  = detect_new_key(raw_text, semitones, use_flats, notation)
        filename = build_filename(song_name, semitones, new_key, ".md")
        content  = build_markdown(lines, song_name, semitones, new_key, notation)
        return {"ok": True, "content": content, "filename": filename}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def prepare_chordpro(
    raw_text:  str,
    lines:     list[dict],
    song_name: str,
    semitones: int,
    use_flats: bool,
    notation:  str,
) -> dict:
    """Build ChordPro content + suggested filename."""
    try:
        new_key  = detect_new_key(raw_text, semitones, use_flats, notation)
        filename = build_filename(song_name, semitones, new_key, ".cho")
        content  = build_chordpro(lines, song_name, new_key)
        return {"ok": True, "content": content, "filename": filename}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def prepare_pdf(
    raw_text:    str,
    lines:       list[dict],
    song_name:   str,
    semitones:   int,
    use_flats:   bool,
    notation:    str,
    chord_color: str = "#f9a825",
) -> dict:
    """Build PDF bytes + suggested filename."""
    try:
        new_key  = detect_new_key(raw_text, semitones, use_flats, notation)
        filename = build_filename(song_name, semitones, new_key, ".pdf")
        pdf_bytes = build_pdf(lines, song_name, semitones, new_key, chord_color)
        return {"ok": True, "bytes": pdf_bytes, "filename": filename}
    except ImportError:
        return {
            "ok": False,
            "error": (
                "PDF export requires fpdf2.\n"
                "Install it with:  pip install fpdf2"
            ),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
