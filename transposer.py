# transposer.py
# Core chord transposition engine

import re

# ── Chromatic scales ────────────────────────────────────────────────────────

SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS  = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Enharmonic normalisation → index in SHARPS list
ENHARMONIC = {
    "C":  0, "B#": 0,
    "C#": 1, "Db": 1,
    "D":  2,
    "D#": 3, "Eb": 3,
    "E":  4, "Fb": 4,
    "F":  5, "E#": 5,
    "F#": 6, "Gb": 6,
    "G":  7,
    "G#": 8, "Ab": 8,
    "A":  9,
    "A#": 10, "Bb": 10,
    "B":  11, "Cb": 11,
}

# Latin (solfège) notation
LATIN_SHARPS = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]
LATIN_FLATS  = ["Do", "Reb", "Re", "Mib", "Mi", "Fa", "Solb","Sol", "Lab",  "La", "Sib", "Si"]

# ── Chord regex ─────────────────────────────────────────────────────────────
#
# Groups:
#   root       – A-G
#   accidental – # or b (optional)
#   modifier   – everything that follows (maj7, m, dim, sus2, …) up to slash
#   slash      – /
#   bass_root  – bass note root
#   bass_acc   – bass note accidental
#
# The regex is intentionally NOT anchored so it can be used inside a larger
# token-scanning loop.

CHORD_RE = re.compile(
    r"""
    (?<![A-Za-z])           # not preceded by a letter (avoids words like "Ahora")
    (?P<root>[A-G])         # root note  A-G
    (?P<accidental>[#b]?)   # optional sharp (#) or flat (b)
    (?P<modifier>
        # ── Primary quality keyword ──────────────────────────────────────────
        (?:maj|min|aug|dim|sus|add|dom|M|m)?

        # ── Numeric extension  7 / 9 / 11 / 13 ──────────────────────────────
        \d*

        # ── Optional secondary keyword + number  (e.g. maj7, sus4) ──────────
        (?:maj|min|aug|dim|sus|add)?\d*

        # ── Parenthesised alterations  e.g. (b5)  (b13)  (#11) ─────────────
        (?:\([#b]?\d+(?:[,/][#b]?\d+)*\))*

        # ── Trailing single-char modifier  e.g. +  for augmented ────────────
        [+]?
    )
    (?:
        /                                     # slash chord separator  C/G
        (?P<bass_root>[A-G])
        (?P<bass_acc>[#b]?)
    )?
    (?![A-Za-z])            # not followed by a letter — rejects "Ahora", "Dm7th…"
    """,
    re.VERBOSE,
)

# Words that look like chords but aren't (heuristic list)
FALSE_POSITIVES = {
    "Am", "Be", "Bb",          # common false hits in prose – keep Am (it IS a chord)
    "A", "B", "C", "D",        # bare single letters in prose are often not chords
                                # we allow them through and rely on context later
}

# If a "chord" token is just a single capital letter followed by nothing and
# sits inside a prose word context we skip it.  However in chord sheets bare
# single-letter chords ARE valid (C, G, F …).  We leave that decision to the
# caller / renderer which has line-context.


def note_to_index(root: str, accidental: str) -> int:
    """Return the chromatic index (0-11) for a root+accidental pair."""
    key = root + accidental
    return ENHARMONIC.get(key, ENHARMONIC.get(root, 0))


def index_to_note(index: int, use_flats: bool, notation: str) -> str:
    """Return the note name for a chromatic index."""
    index = index % 12
    if notation == "latin":
        return LATIN_FLATS[index] if use_flats else LATIN_SHARPS[index]
    return FLATS[index] if use_flats else SHARPS[index]


def transpose_chord(match: re.Match, semitones: int, use_flats: bool, notation: str) -> str:
    """
    Given a regex match object from CHORD_RE, transpose the chord by
    `semitones` and return the new chord string.
    """
    root      = match.group("root")
    accidental= match.group("accidental") or ""
    modifier  = match.group("modifier")   or ""
    bass_root = match.group("bass_root")
    bass_acc  = match.group("bass_acc")   or ""

    # Transpose main root
    idx         = note_to_index(root, accidental)
    new_root    = index_to_note((idx + semitones) % 12, use_flats, notation)

    # Transpose bass note (slash chord)
    new_bass = ""
    if bass_root:
        bidx     = note_to_index(bass_root, bass_acc)
        new_bass = "/" + index_to_note((bidx + semitones) % 12, use_flats, notation)

    return new_root + modifier + new_bass


def is_chord_line(line: str) -> bool:
    """
    Heuristic: a line is a 'chord line' if the ratio of chord-token characters
    to total non-space characters is high (> 60 %).
    """
    stripped = line.strip()
    if not stripped:
        return False

    chord_chars = 0
    for m in CHORD_RE.finditer(stripped):
        chord_chars += len(m.group(0))

    non_space = len(stripped.replace(" ", ""))
    if non_space == 0:
        return False

    return (chord_chars / non_space) > 0.6


def transpose_text(
    text: str,
    semitones: int,
    notation: str  = "american",
    use_flats: bool = False,
) -> list[dict]:
    """
    Transpose all chords in `text`.

    Returns a list of 'line' objects:
        {
            "original": str,
            "tokens":   [ {"type": "chord"|"text", "value": str}, … ]
        }

    `tokens` contains the transposed line split into chord / plain-text
    segments so the renderer can highlight chords individually.
    """
    lines = text.splitlines()
    result = []

    for line in lines:
        tokens = []
        last   = 0

        for m in CHORD_RE.finditer(line):
            start, end = m.span()

            # Plain text before this chord
            if start > last:
                tokens.append({"type": "text", "value": line[last:start]})

            transposed = transpose_chord(m, semitones, use_flats, notation)
            tokens.append({"type": "chord", "value": transposed, "original": m.group(0)})
            last = end

        # Remaining plain text
        if last < len(line):
            tokens.append({"type": "text", "value": line[last:]})

        result.append({"original": line, "tokens": tokens})

    return result
