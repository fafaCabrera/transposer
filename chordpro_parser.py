# chordpro_parser.py
# ChordPro (.cho / .chopro) parser.
# Converts ChordPro format → plain-text chord-above-lyric so it flows through
# the existing transposer pipeline unchanged.

from __future__ import annotations

import re

DIRECTIVE_RE    = re.compile(r'^\s*\{([^:}\n]+)(?::([^}\n]*))?\}\s*$', re.I)
INLINE_CHORD_RE = re.compile(r'\[([^\]\[]+)\]')

_SECTION_START: dict[str, str] = {
    'verse':          'Verse',
    'chorus':         'Chorus',
    'bridge':         'Bridge',
    'tab':            'Tab',
    'grid':           'Grid',
    'pre_chorus':     'Pre-Chorus',
    'intro':          'Intro',
    'outro':          'Outro',
    'interlude':      'Interlude',
    'instrumental':   'Instrumental',
    'middle':         'Middle',
    'solo':           'Solo',
}
# short-form start_of_* aliases: sov→verse, soc→chorus, sob→bridge
_SOX_SHORT = {
    'v': 'verse', 'c': 'chorus', 'b': 'bridge',
    't': 'tab',   'g': 'grid',
}


def parse_chordpro(text: str) -> dict:
    """
    Parse a ChordPro document.

    Returns:
        {
            "ok":         True,
            "plain_text": str,
            "meta":       {"title", "artist", "key", "capo", "tempo"},
        }
    """
    meta: dict = {
        "title": None, "artist": None,
        "key":   None, "capo":   None, "tempo": None,
    }
    out: list[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        dm   = DIRECTIVE_RE.match(line.strip())
        if dm:
            k = dm.group(1).strip().lower().replace('-', '_')
            v = (dm.group(2) or "").strip()
            _handle_directive(k, v, meta, out)
            continue

        if INLINE_CHORD_RE.search(line):
            chord_line, lyric_line = _split_inline(line)
            if chord_line.strip():
                out.append(chord_line)
            out.append(lyric_line)
        else:
            out.append(line)

    plain = re.sub(r'\n{3,}', '\n\n', "\n".join(out)).strip()
    return {"ok": True, "plain_text": plain, "meta": meta}


def _handle_directive(k: str, v: str, meta: dict, out: list[str]) -> None:
    # ── Metadata ─────────────────────────────────────────────────────────────
    if k in ('title', 't'):
        meta['title'] = v
        if v:
            out.append(f"# {v}")
    elif k in ('artist', 'composer', 'a'):
        if k == 'artist':
            meta['artist'] = v
        if v:
            out.append(f"   {v}")
    elif k in ('subtitle', 'st', 'album', 'lyricist', 'arranger'):
        if v:
            out.append(f"   {v}")
    elif k == 'key':
        meta['key'] = v
    elif k == 'capo':
        meta['capo'] = v
    elif k == 'tempo':
        meta['tempo'] = v

    # ── Comments ──────────────────────────────────────────────────────────────
    elif k in ('comment', 'c', 'comment_italic', 'ci', 'comment_box', 'cb'):
        if v:
            out.append(f"// {v}")

    # ── Section markers ───────────────────────────────────────────────────────
    elif k.startswith('start_of_') or (
        k.startswith('so') and len(k) == 3 and k[2] in _SOX_SHORT
    ):
        if k.startswith('start_of_'):
            section_key = k[9:]
        else:
            section_key = _SOX_SHORT.get(k[2:], k[2:])
        label = v or _SECTION_START.get(
            section_key,
            section_key.replace('_', ' ').title(),
        )
        out.append(f"\n[{label}]")

    elif k.startswith('end_of_') or (
        k.startswith('eo') and len(k) == 3 and k[2] in _SOX_SHORT
    ):
        out.append("")

    elif k in ('new_page', 'np', 'new_physical_page', 'npp'):
        out.append("\n---\n")


def _split_inline(line: str) -> tuple[str, str]:
    """
    [Am]Lyric [G]text  →  ("Am     G    ", "Lyric text  ")

    Extracts chord names at their column positions, returns a chord line
    and a lyric line (both plain text, ready for transposer pipeline).
    """
    chords_at: list[tuple[int, str]] = []
    lyric_parts: list[str] = []
    lyric_col = 0
    last = 0

    for m in INLINE_CHORD_RE.finditer(line):
        before = line[last:m.start()]
        lyric_parts.append(before)
        lyric_col += len(before)
        chords_at.append((lyric_col, m.group(1)))
        last = m.end()

    lyric_parts.append(line[last:])
    lyric = "".join(lyric_parts)

    if not chords_at:
        return ("", lyric)

    need = max(col + len(ch) for col, ch in chords_at)
    buf  = [" "] * max(need + 2, len(lyric))
    for col, chord in chords_at:
        for i, ch in enumerate(chord):
            idx = col + i
            if idx < len(buf):
                buf[idx] = ch
            else:
                buf += [" "] * (idx - len(buf)) + [ch]

    return ("".join(buf).rstrip(), lyric)


def is_chordpro(text: str) -> bool:
    """Quick heuristic: does this text look like ChordPro?"""
    for line in text.splitlines()[:30]:
        stripped = line.strip()
        if DIRECTIVE_RE.match(stripped):
            return True
        # Inline chord syntax counts too
        if INLINE_CHORD_RE.search(stripped):
            return True
    return False
