# cleaners.py
# Site-specific HTML extractors for chord/lyric websites.
# Handles: Ultimate Guitar, Cifraclub, lacuerda.net

from __future__ import annotations

import json
import re


# ── Public dispatcher ─────────────────────────────────────────────────────────

def dispatch_cleaner(url: str, html: str) -> str | None:
    """
    Route a URL to the appropriate site-specific cleaner.

    Returns cleaned plain text, or None if no site-specific cleaner matched
    (caller should fall back to generic HTML extraction).
    """
    hostname = ""
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or ""
    except Exception:
        pass

    if "ultimate-guitar.com" in hostname:
        return clean_ultimate_guitar(html)
    if "cifraclub.com" in hostname or "cifraclub.com.br" in hostname:
        return clean_cifraclub(html)
    if "lacuerda.net" in hostname:
        return clean_lacuerda(html)

    return None


# ── Ultimate Guitar ───────────────────────────────────────────────────────────

def clean_ultimate_guitar(html: str) -> str | None:
    """
    Extract chord-sheet text from an Ultimate Guitar page.

    Strategy:
      1. Parse window.UGAPP JSON blob embedded in the page script
      2. Regex-scan for a "content" JSON string containing [ch] markup
    Returns None on failure.
    """
    # Strategy 1: JSON extraction from window.UGAPP
    m = re.search(
        r"window\.UGAPP\.store\.page\.data\s*=\s*(\{.{20,}\})\s*;",
        html,
        re.DOTALL,
    )
    if m:
        try:
            data    = json.loads(m.group(1))
            content = (
                _dig(data, "tab_view", "wiki_tab", "content")
                or _dig(data, "tab", "content")
                or ""
            )
            if content:
                return _strip_ug_markup(content)
        except Exception:
            pass

    # Strategy 2: scan for a JSON-encoded "content" string with UG markup
    for cm in re.finditer(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', html):
        try:
            content = json.loads('"' + cm.group(1) + '"')
        except Exception:
            continue
        if "[ch]" in content or "[tab]" in content:
            return _strip_ug_markup(content)

    return None


def _dig(d: dict, *keys: str):
    """Safely traverse nested dicts."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _strip_ug_markup(content: str) -> str:
    """Remove UG-specific markup, keeping readable chord/lyric text."""
    # [ch]Am[/ch] → Am  (chord markers)
    content = re.sub(r"\[ch\](.*?)\[/ch\]", r"\1", content, flags=re.DOTALL)
    # [tab]...[/tab] → keep content
    content = re.sub(r"\[tab\](.*?)\[/tab\]", r"\1", content, flags=re.DOTALL)
    # Section tags like [Verse 1], [Chorus], etc.
    content = re.sub(
        r"\[(?:verse|chorus|bridge|intro|outro|pre-?chorus|interlude|solo"
        r"|instrumental|other|break|ending|hook|refrain)[^\]]*\]",
        "",
        content,
        flags=re.I,
    )
    # JSON escape sequences
    content = content.replace("\\n", "\n").replace("\\r", "").replace("\\t", "\t")
    # Normalise blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


# ── Cifraclub ─────────────────────────────────────────────────────────────────

def clean_cifraclub(html: str) -> str | None:
    """
    Extract chord-sheet text from a Cifraclub page.
    Returns None on failure.
    """
    # BeautifulSoup path
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")

        # Primary container: <pre class="cifra"> or any <pre>
        pre = soup.find("pre", class_=re.compile(r"cifra", re.I)) or soup.find("pre")
        if pre:
            text = pre.get_text("\n")
            if text.strip():
                return _clean_generic_text(text)

        # Fallback: div with class containing "cifra"
        div = soup.find(True, class_=re.compile(r"cifra", re.I))
        if div:
            text = div.get_text("\n")
            if text.strip():
                return _clean_generic_text(text)

    except ImportError:
        # Regex fallback
        m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL | re.I)
        if m:
            text = re.sub(r"<[^>]+>", "", m.group(1))
            if text.strip():
                return _clean_generic_text(text)

    return None


# ── lacuerda.net ──────────────────────────────────────────────────────────────

def clean_lacuerda(html: str) -> str | None:
    """
    Extract chord-sheet text from lacuerda.net.
    Returns None on failure.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")

        # lacuerda uses id/class variants of "texto", "cancion", or similar
        for attrs in [
            {"id":    re.compile(r"texto|cancion|lyric|chord|tab", re.I)},
            {"class": re.compile(r"texto|cancion|lyric|chord|tab",  re.I)},
        ]:
            el = soup.find(True, attrs=attrs)
            if el:
                text = el.get_text("\n")
                if text.strip():
                    return _clean_generic_text(text)

        # Fallback: any <pre>
        pre = soup.find("pre")
        if pre:
            text = pre.get_text("\n")
            if text.strip():
                return _clean_generic_text(text)

    except ImportError:
        m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL | re.I)
        if m:
            text = re.sub(r"<[^>]+>", "", m.group(1))
            if text.strip():
                return _clean_generic_text(text)

    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_generic_text(text: str) -> str:
    """Normalise line endings and collapse excess blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
