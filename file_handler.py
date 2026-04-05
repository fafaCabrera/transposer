# file_handler.py
# Bridge between the UI file-upload flow and the parser module.
# Handles: base64 uploads, native file paths, .lnk shortcuts, and URLs.

from __future__ import annotations

import base64
import os
import re
import sys
import tempfile

from parser import extract_text


# ── Base64 upload (drag-drop / <input type=file>) ─────────────────────────────

def handle_file_upload(filename: str, b64_data: str) -> dict:
    """
    Receive a file uploaded from the browser (filename + base64 content),
    write it to a temp file, extract its text, and return the result.

    Returns {"ok": True, "text": "…"} or {"ok": False, "error": "…"}.
    """
    try:
        raw = base64.b64decode(b64_data)
    except Exception as exc:
        return {"ok": False, "error": f"Base64 decode error: {exc}"}

    ext = os.path.splitext(filename)[1].lower()

    # Transparently resolve the real target for .lnk uploads
    if ext == ".lnk":
        return {"ok": False, "error": "Drag the target file directly, not the shortcut."}

    allowed = {".txt", ".pdf", ".docx", ".rtf"}
    if ext not in allowed:
        return {"ok": False, "error": f"Unsupported file type '{ext}'."}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        text = extract_text(tmp_path)
        return {"ok": True, "text": text}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── Native file path (open dialog / CLI arg) ──────────────────────────────────

def handle_file_path(path: str) -> dict:
    """
    Extract text from a file specified by its absolute path.
    Automatically resolves Windows .lnk shortcuts.

    Returns {"ok": True, "text": "…"} or {"ok": False, "error": "…"}.
    """
    if not path:
        return {"ok": False, "error": "Empty path."}

    # Resolve .lnk shortcuts
    ext = os.path.splitext(path)[1].lower()
    if ext == ".lnk":
        try:
            path = resolve_lnk(path)
        except Exception as exc:
            return {"ok": False, "error": f"Cannot resolve shortcut: {exc}"}

    if not os.path.isfile(path):
        return {"ok": False, "error": f"File not found: '{path}'"}

    try:
        text = extract_text(path)
        return {"ok": True, "text": text}
    except (ValueError, IOError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Unexpected error: {exc}"}


# ── Windows .lnk shortcut resolver ───────────────────────────────────────────

def resolve_lnk(lnk_path: str) -> str:
    """
    Resolve a Windows Shell Link (.lnk) to its target file path.

    Strategy (in order):
      1. PowerShell WScript.Shell COM object  (Windows, no extra deps)
      2. winshell library                      (optional)
      3. Manual binary parser                  (fallback, covers simple cases)

    Raises IOError if resolution fails or we're not on Windows.
    """
    if sys.platform != "win32":
        raise IOError(".lnk shortcut resolution is only supported on Windows.")

    # ── Strategy 1: PowerShell (most reliable, zero extra deps) ──────────────
    try:
        import subprocess
        escaped = lnk_path.replace("'", "''")
        ps_cmd  = (
            f"(New-Object -ComObject WScript.Shell)"
            f".CreateShortcut('{escaped}').TargetPath"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        target = result.stdout.strip()
        if target and os.path.exists(target):
            return target
    except Exception:
        pass

    # ── Strategy 2: winshell library ─────────────────────────────────────────
    try:
        import winshell  # type: ignore
        target = winshell.shortcut(lnk_path).path
        if target and os.path.exists(target):
            return target
    except ImportError:
        pass

    # ── Strategy 3: manual binary parse (simple .lnk files only) ─────────────
    try:
        target = _parse_lnk_binary(lnk_path)
        if target and os.path.exists(target):
            return target
    except Exception:
        pass

    raise IOError(
        f"Could not resolve shortcut target from '{lnk_path}'. "
        "Make sure the target file still exists."
    )


def _parse_lnk_binary(path: str) -> str:
    """
    Minimal .lnk parser — extracts the LocalBasePath string from the
    StringData section of a Shell Link Binary File Format file.
    Covers the most common case of a local file shortcut.
    """
    import struct

    with open(path, "rb") as fh:
        data = fh.read()

    # Verify LNK magic (0x4C000000) and CLSID
    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        raise ValueError("Not a valid .lnk file")

    # LinkFlags at offset 0x14
    link_flags = struct.unpack_from("<I", data, 0x14)[0]
    HAS_LINK_TARGET_ID_LIST = bool(link_flags & 0x01)
    HAS_LINK_INFO           = bool(link_flags & 0x02)
    IS_UNICODE              = bool(link_flags & 0x80)

    offset = 76  # HeaderSize is always 0x4C

    # Skip LinkTargetIDList if present
    if HAS_LINK_TARGET_ID_LIST:
        id_list_size = struct.unpack_from("<H", data, offset)[0]
        offset += 2 + id_list_size

    # Parse LinkInfo if present
    if HAS_LINK_INFO:
        li_size = struct.unpack_from("<I", data, offset)[0]
        li_flags = struct.unpack_from("<I", data, offset + 4)[0]
        off_local = struct.unpack_from("<I", data, offset + 16)[0]

        # LocalBasePath (ANSI) or LocalBasePathOffsetUnicode
        if li_flags & 0x01:  # VolumeIDAndLocalBasePath
            base_path_off = offset + off_local
            end = data.index(b"\x00", base_path_off)
            return data[base_path_off:end].decode("mbcs", errors="replace")

        offset += li_size

    raise ValueError("LocalBasePath not found in .lnk file")


# ── URL fetcher ───────────────────────────────────────────────────────────────

def fetch_url(url: str) -> dict:
    """
    Fetch a URL and extract clean text (lyrics + chords).

    HTML is stripped; scripts, nav, ads, and footer elements are removed.
    Returns {"ok": True, "text": "…"} or {"ok": False, "error": "…"}.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        html = _download_html(url)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to fetch URL: {exc}"}

    try:
        text = _html_to_text(html)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to parse HTML: {exc}"}

    text = _clean_text(text)

    if len(text.strip()) < 20:
        return {"ok": False, "error": "Page appears to contain no readable text."}

    return {"ok": True, "text": text}


def _download_html(url: str) -> str:
    """Download a URL as a string, trying requests then urllib."""
    # ── requests (preferred) ─────────────────────────────────────────────────
    try:
        import requests  # type: ignore
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except ImportError:
        pass

    # ── urllib.request (stdlib fallback) ─────────────────────────────────────
    import urllib.request
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ChordTransposer/1.0)"
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _html_to_text(html: str) -> str:
    """
    Strip HTML and return clean plain text.

    Uses BeautifulSoup if available; falls back to a stdlib HTMLParser.
    """
    # ── BeautifulSoup (best quality) ─────────────────────────────────────────
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")

        # Remove noise elements
        for tag in soup(
            ["script", "style", "noscript", "nav", "footer",
             "header", "aside", "iframe", "form", "button",
             "advertisement", "ads"]
        ):
            tag.decompose()

        # Remove elements by common ad/nav class/id patterns
        for pattern in ["nav", "menu", "ad", "banner", "sidebar",
                        "footer", "header", "cookie", "popup"]:
            for el in soup.find_all(
                True,
                attrs={
                    "class": re.compile(pattern, re.I),
                    "id":    re.compile(pattern, re.I),
                }
            ):
                el.decompose()

        # Try to find main content
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id=re.compile(r"content|lyrics|main", re.I))
            or soup.find(class_=re.compile(r"content|lyrics|main", re.I))
            or soup.body
            or soup
        )

        return main.get_text(separator="\n")

    except ImportError:
        pass

    # ── stdlib fallback ───────────────────────────────────────────────────────
    return _html_to_text_stdlib(html)


def _html_to_text_stdlib(html: str) -> str:
    """Minimal HTML → text using stdlib html.parser."""
    from html.parser import HTMLParser

    class _Extractor(HTMLParser):
        SKIP_TAGS = {
            "script", "style", "noscript", "nav", "footer",
            "header", "aside", "iframe", "form",
        }

        def __init__(self):
            super().__init__()
            self._skip = 0
            self.parts: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() in self.SKIP_TAGS:
                self._skip += 1

        def handle_endtag(self, tag):
            if tag.lower() in self.SKIP_TAGS and self._skip:
                self._skip -= 1
            if tag.lower() in ("p", "br", "div", "li", "tr", "h1",
                               "h2", "h3", "h4", "h5"):
                if not self._skip:
                    self.parts.append("\n")

        def handle_data(self, data):
            if not self._skip:
                self.parts.append(data)

    parser = _Extractor()
    parser.feed(html)
    return "".join(parser.parts)


# ── Text cleaning ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """
    Normalise whitespace and remove duplicate / garbage lines.

    - Collapse runs of spaces/tabs within a line
    - Remove lines that are pure punctuation / single chars (likely nav debris)
    - Collapse triple+ blank lines to a single blank line
    - Remove exact duplicate consecutive lines
    """
    lines = text.splitlines()
    cleaned:   list[str] = []
    prev_line: str = ""

    for raw in lines:
        line = raw.rstrip()

        # Collapse multiple spaces/tabs (preserving leading indent)
        stripped = line.lstrip()
        indent   = line[: len(line) - len(stripped)]
        stripped = re.sub(r"[ \t]{2,}", " ", stripped)
        line     = indent + stripped

        # Skip very short noise lines (single char, just punctuation)
        if re.fullmatch(r"[^\w]*", line) and len(line) < 3:
            continue

        # Skip exact duplicate consecutive lines
        if line and line == prev_line:
            continue

        cleaned.append(line)
        prev_line = line

    # Collapse runs of 3+ blank lines
    result: list[str] = []
    blank_run = 0
    for line in cleaned:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                result.append(line)
        else:
            blank_run = 0
            result.append(line)

    return "\n".join(result)
