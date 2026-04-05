# parser.py
# Text extraction from various file formats: .txt, .pdf, .docx, .rtf
# Uses only the standard library where possible.

from __future__ import annotations

import os
import re
import zlib
import zipfile


# ── Public entry point ───────────────────────────────────────────────────────

def extract_text(path: str) -> str:
    """
    Extract plain text from *path*.

    Supported extensions: .txt  .pdf  .docx  .rtf
    Raises ValueError for unsupported types, IOError for read failures.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".txt":
        return _read_txt(path)
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".rtf":
        return _read_rtf(path)

    raise ValueError(f"Unsupported file type: '{ext}'")


# ── TXT ──────────────────────────────────────────────────────────────────────

def _read_txt(path: str) -> str:
    """Read a plain-text file, trying UTF-8 then latin-1 as fallback."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
    raise IOError(f"Cannot decode '{path}' as text.")


# ── PDF ──────────────────────────────────────────────────────────────────────

def _read_pdf(path: str) -> str:
    """
    Extract text from a PDF.

    Strategy (in order):
      1. pdfminer.six  – best quality, optional
      2. pypdf         – good quality, optional
      3. Built-in      – pure stdlib, handles most simple/text PDFs
    """
    # ── pdfminer.six ────────────────────────────────────────────────────────
    try:
        from pdfminer.high_level import extract_text as _pm_extract
        text = _pm_extract(path)
        if text and text.strip():
            return text
    except ImportError:
        pass
    except Exception:
        pass

    # ── pypdf ────────────────────────────────────────────────────────────────
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        pages  = [p.extract_text() or "" for p in reader.pages]
        text   = "\n".join(pages)
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception:
        pass

    # ── built-in stdlib extractor ────────────────────────────────────────────
    try:
        text = _pdf_builtin(path)
        if text.strip():
            return text
    except Exception as exc:
        raise IOError(
            f"Could not extract text from PDF: {exc}\n"
            "Tip: install 'pdfminer.six' for reliable PDF support:  "
            "pip install pdfminer.six"
        )

    raise IOError(
        "PDF appears to contain no extractable text (may be image-only).\n"
        "Install 'pdfminer.six' for broader PDF support."
    )


def _pdf_builtin(path: str) -> str:
    """
    Pure-Python PDF text extractor.

    Handles:
      - Parenthesis strings  (Hello World) Tj
      - Hex strings          <48656c6c6f> Tj
      - Array operator       [(Hello) (World)] TJ
      - FlateDecode (zlib) compressed content streams
      - Basic PDF string escape sequences
    """
    with open(path, "rb") as fh:
        raw = fh.read()

    # ── Step 1: decompress FlateDecode streams ───────────────────────────────
    # Collect raw bytes + all successfully decompressed stream bodies
    chunks: list[bytes] = [raw]

    # Match object dictionaries + their streams so we can check /Filter
    stream_re = re.compile(
        rb"<<([^>]{0,2000}?)>>\s*stream\r?\n(.*?)endstream",
        re.DOTALL,
    )

    for m in stream_re.finditer(raw):
        header = m.group(1)
        body   = m.group(2)

        # Only attempt decompression when the stream declares FlateDecode
        if b"FlateDecode" not in header and b"Fl" not in header:
            continue

        for wbits in (15, -15, 47):  # zlib, raw deflate, gzip
            try:
                decompressed = zlib.decompress(body, wbits)
                chunks.append(decompressed)
                break
            except Exception:
                continue

    all_data = b"\n".join(chunks)

    # ── Step 2: extract text from BT…ET blocks ───────────────────────────────
    parts: list[str] = []

    for block in re.findall(rb"BT(.*?)ET", all_data, re.DOTALL):
        _extract_block_text(block, parts)
        parts.append("\n")

    text = "".join(parts)
    # Clean up excessive whitespace while preserving structure
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_block_text(block: bytes, out: list[str]) -> None:
    """Extract all text tokens from a single BT…ET block into `out`."""

    # ── Tj / ' operator: single string ──────────────────────────────────────

    # Parenthesis strings
    for m in re.finditer(
        rb"\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*(?:Tj|\'|\")", block
    ):
        out.append(_decode_pdf_paren_string(m.group(1)))

    # Hex strings
    for m in re.finditer(rb"<([0-9a-fA-F\s]+)>\s*(?:Tj|\'|\")", block):
        out.append(_decode_pdf_hex_string(m.group(1)))

    # ── TJ operator: array of strings and kerning numbers ───────────────────

    for arr_m in re.finditer(rb"\[([^\]]*)\]\s*TJ", block):
        arr = arr_m.group(1)

        for m in re.finditer(rb"\(([^)\\]*(?:\\.[^)\\]*)*)\)", arr):
            out.append(_decode_pdf_paren_string(m.group(1)))

        for m in re.finditer(rb"<([0-9a-fA-F\s]+)>", arr):
            out.append(_decode_pdf_hex_string(m.group(1)))


def _decode_pdf_paren_string(b: bytes) -> str:
    """Decode a raw PDF parenthesis-delimited string (handles escape seqs)."""
    result = bytearray()
    i = 0
    while i < len(b):
        if b[i:i+1] == b"\\" and i + 1 < len(b):
            nxt = b[i + 1:i + 2]
            if   nxt == b"n":  result.append(10);  i += 2
            elif nxt == b"r":  result.append(13);  i += 2
            elif nxt == b"t":  result.append(9);   i += 2
            elif nxt in (b"\\", b"(", b")"):
                result.append(nxt[0]); i += 2
            else:
                # Octal escape \ddd
                octal = b[i + 1:i + 4]
                if octal and octal[0:1].isdigit():
                    try:
                        result.append(int(octal[:3], 8))
                        i += 4
                    except ValueError:
                        i += 2
                else:
                    i += 2
        else:
            result.append(b[i])
            i += 1

    return _pdf_bytes_to_str(bytes(result))


def _decode_pdf_hex_string(b: bytes) -> str:
    """Decode a hex-encoded PDF string <4865 6c6c 6f>."""
    hex_clean = b.replace(b" ", b"").replace(b"\n", b"").replace(b"\r", b"")
    if len(hex_clean) % 2:
        hex_clean += b"0"  # PDF spec: odd length pads with 0
    try:
        raw = bytes.fromhex(hex_clean.decode("ascii", errors="ignore"))
        return _pdf_bytes_to_str(raw)
    except Exception:
        return ""


def _pdf_bytes_to_str(b: bytes) -> str:
    """Try UTF-16-BE (common in modern PDFs), then latin-1."""
    if len(b) >= 2 and b[:2] in (b"\xfe\xff", b"\xff\xfe"):
        try:
            return b.decode("utf-16")
        except Exception:
            pass
    try:
        return b.decode("latin-1")
    except Exception:
        return b.decode("utf-8", errors="replace")


# ── DOCX ─────────────────────────────────────────────────────────────────────
# A .docx file is a ZIP archive; text lives in word/document.xml.

def _read_docx(path: str) -> str:
    """Extract plain text from a .docx file using stdlib only."""
    import xml.etree.ElementTree as ET

    WNS   = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    TAG_P = f"{{{WNS}}}p"
    TAG_T = f"{{{WNS}}}t"
    TAG_BR = f"{{{WNS}}}br"

    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
    except KeyError:
        raise IOError("Invalid .docx file: missing word/document.xml")
    except zipfile.BadZipFile:
        raise IOError("File is not a valid .docx (bad ZIP structure).")

    tree       = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []

    for para in tree.iter(TAG_P):
        texts: list[str] = []
        for child in para.iter():
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if local == "t" and child.text:
                texts.append(child.text)
            elif local == "br":
                texts.append("\n")
        paragraphs.append("".join(texts))

    if not paragraphs:
        paragraphs = _docx_fallback(tree)

    return "\n".join(paragraphs)


def _docx_fallback(tree) -> list[str]:
    """Namespace-agnostic text extraction for non-standard DOCX variants."""
    paragraphs: list[str] = []
    for elem in tree.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local == "p":
            texts = []
            for child in elem.iter():
                cl = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if cl == "t" and child.text:
                    texts.append(child.text)
            paragraphs.append("".join(texts))
    return paragraphs


# ── RTF ──────────────────────────────────────────────────────────────────────
# RTF is text-based; we strip control words with a small state machine.

def _read_rtf(path: str) -> str:
    """Extract plain text from an RTF file using a pure-Python parser."""
    for enc in ("utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc, errors="replace") as fh:
                raw = fh.read()
            break
        except Exception:
            continue
    else:
        raise IOError(f"Cannot read '{path}'")

    return _rtf_to_text(raw)


def _rtf_to_text(rtf: str) -> str:
    """
    Strip RTF markup and return plain text.

    Handles:
      - Brace depth tracking
      - Ignorable destinations {\\* ...}
      - Control words: \\par \\line \\tab \\' (hex char) etc.
      - Unicode escapes \\uNNNN
    """
    output: list[str] = []
    i             = 0
    depth         = 0
    ignore_depth: int | None = None
    n             = len(rtf)

    while i < n:
        ch = rtf[i]

        if ch == "{":
            depth += 1
            i += 1
            # Detect ignorable destination {\* ...}
            if i < n and rtf[i] == "\\":
                j = i
                while j < n and rtf[j] not in (" ", "{", "}", "\r", "\n"):
                    j += 1
                if rtf[i:j] == "\\*":
                    ignore_depth = depth
            continue

        if ch == "}":
            if ignore_depth is not None and depth == ignore_depth:
                ignore_depth = None
            depth -= 1
            i += 1
            continue

        if ignore_depth is not None:
            i += 1
            continue

        if ch == "\\":
            i += 1
            if i >= n:
                break

            nxt = rtf[i]

            if nxt == "\\":
                output.append("\\"); i += 1
            elif nxt == "{":
                output.append("{");  i += 1
            elif nxt == "}":
                output.append("}");  i += 1
            elif nxt == "\n":
                output.append("\n"); i += 1
            elif nxt == "\r":
                i += 1
            elif nxt == "'":
                # Hex character \'XX
                if i + 2 < n:
                    try:
                        output.append(chr(int(rtf[i+1:i+3], 16)))
                    except ValueError:
                        pass
                    i += 3
                else:
                    i += 1
            elif nxt == "u":
                # Unicode escape \uNNNN (followed by replacement char)
                j = i + 1
                if j < n and (rtf[j].isdigit() or rtf[j] == "-"):
                    k = j
                    if rtf[k] == "-":
                        k += 1
                    while k < n and rtf[k].isdigit():
                        k += 1
                    try:
                        codepoint = int(rtf[j:k])
                        if codepoint < 0:
                            codepoint += 65536
                        output.append(chr(codepoint))
                    except (ValueError, OverflowError):
                        pass
                    i = k
                    # Skip one replacement character that follows
                    if i < n and rtf[i] == " ":
                        i += 1
                else:
                    i += 1
            elif nxt.isalpha() or nxt == "-":
                j = i
                if rtf[j] == "-":
                    j += 1
                while j < n and rtf[j].isalpha():
                    j += 1
                word = rtf[i:j]
                # Optional numeric parameter
                k = j
                if k < n and (rtf[k].isdigit() or rtf[k] == "-"):
                    while k < n and (rtf[k].isdigit() or rtf[k] == "-"):
                        k += 1
                if k < n and rtf[k] == " ":
                    k += 1  # consume trailing space delimiter

                if   word == "par":      output.append("\n\n")
                elif word == "line":     output.append("\n")
                elif word == "tab":      output.append("\t")
                elif word == "endash":   output.append("–")
                elif word == "emdash":   output.append("—")
                elif word == "lquote":   output.append("\u2018")
                elif word == "rquote":   output.append("\u2019")
                elif word == "ldblquote":output.append("\u201C")
                elif word == "rdblquote":output.append("\u201D")
                # All other control words are skipped

                i = k
            else:
                i += 1
            continue

        if ch != "\r":
            output.append(ch)
        i += 1

    text = "".join(output)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
