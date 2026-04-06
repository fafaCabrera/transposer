# parser.py
# Text extraction from various file formats: .txt, .pdf, .docx, .rtf
# Uses only the standard library where possible; optionally uses
# pdfminer.six, pypdf, pytesseract, pdf2image, or pymupdf for PDFs.

from __future__ import annotations

import os
import re
import zlib
import zipfile



# ── Public entry point ───────────────────────────────────────────────────────

def extract_text(path: str) -> str:
    """
    Extract plain text from *path*.

    Supported extensions: .txt  .md  .pdf  .docx  .rtf
    Raises ValueError for unsupported types, IOError for read failures.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in (".txt", ".md", ".cho", ".chopro", ".url"):
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

    Strategy: try each extractor in order; use the first one that returns
    any non-empty text.  Only attempt OCR if every text extractor returns
    nothing — which is the true signal of an image-based PDF.

    Priority:
      1. pdfminer.six  – best text quality (optional)
      2. pypdf         – second best (optional)
      3. Built-in      – pure stdlib, no extra deps
      4. OCR           – pytesseract, only when all above yield nothing
    """
    # ── pdfminer.six ─────────────────────────────────────────────────────────
    try:
        from pdfminer.high_level import extract_text as _pm_extract
        text = (_pm_extract(path) or "").strip()
        if text:
            return text
    except ImportError:
        pass
    except Exception:
        pass

    # ── pypdf ─────────────────────────────────────────────────────────────────
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        text   = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        if text:
            return text
    except ImportError:
        pass
    except Exception:
        pass

    # ── Built-in stdlib extractor ─────────────────────────────────────────────
    try:
        text = _pdf_builtin(path).strip()
        if text:
            return text
    except Exception:
        pass

    # ── OCR — only reached when all text extractors returned nothing ──────────
    try:
        ocr_text = _apply_ocr(path)
        if ocr_text.strip():
            return ocr_text.strip()
    except ImportError as exc:
        raise IOError(
            "This PDF appears to contain no embedded text (image-based / scanned).\n"
            "To read it, install OCR support:\n"
            "  pip install pytesseract Pillow pymupdf\n"
            "Then install Tesseract:\n"
            "  Windows → https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  macOS   → brew install tesseract\n"
            "  Linux   → sudo apt install tesseract-ocr"
        ) from exc
    except Exception as exc:
        raise IOError(
            f"Could not extract text from this PDF: {exc}\n"
            "The file may be encrypted, corrupted, or image-only."
        ) from exc

    raise IOError(
        "This PDF contains no readable text. "
        "It may be blank, encrypted, or an image-only scan."
    )


# ── Built-in PDF text extractor ───────────────────────────────────────────────

def _pdf_builtin(path: str) -> str:
    """
    Pure-Python PDF text extractor.

    Handles:
      - Parenthesis strings  (Hello World) Tj
      - Hex strings          <48656c6c6f> Tj
      - Array operator       [(Hello) (World)] TJ
      - FlateDecode (zlib) compressed streams
      - Basic PDF string escape sequences
      - UTF-16-BE encoded strings (BOM detection)
    """
    with open(path, "rb") as fh:
        raw = fh.read()

    # Decompress FlateDecode streams
    chunks: list[bytes] = [raw]
    stream_re = re.compile(
        rb"<<([^>]{0,2000}?)>>\s*stream\r?\n(.*?)endstream",
        re.DOTALL,
    )
    for m in stream_re.finditer(raw):
        header = m.group(1)
        body   = m.group(2)
        if b"FlateDecode" not in header and b"Fl" not in header:
            continue
        for wbits in (15, -15, 47):
            try:
                chunks.append(zlib.decompress(body, wbits))
                break
            except Exception:
                continue

    all_data = b"\n".join(chunks)

    parts: list[str] = []
    for block in re.findall(rb"BT(.*?)ET", all_data, re.DOTALL):
        _extract_block_text(block, parts)
        parts.append("\n")

    text = "".join(parts)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_block_text(block: bytes, out: list[str]) -> None:
    """Extract all text tokens from a single BT…ET block into `out`."""
    # Tj / ' with parenthesis strings
    for m in re.finditer(
        rb"\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*(?:Tj|\'|\")", block
    ):
        out.append(_decode_pdf_paren_string(m.group(1)))

    # Tj / ' with hex strings
    for m in re.finditer(rb"<([0-9a-fA-F\s]+)>\s*(?:Tj|\'|\")", block):
        out.append(_decode_pdf_hex_string(m.group(1)))

    # TJ arrays
    for arr_m in re.finditer(rb"\[([^\]]*)\]\s*TJ", block):
        arr = arr_m.group(1)
        for m in re.finditer(rb"\(([^)\\]*(?:\\.[^)\\]*)*)\)", arr):
            out.append(_decode_pdf_paren_string(m.group(1)))
        for m in re.finditer(rb"<([0-9a-fA-F\s]+)>", arr):
            out.append(_decode_pdf_hex_string(m.group(1)))


def _decode_pdf_paren_string(b: bytes) -> str:
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
                octal = b[i + 1:i + 4]
                if octal and octal[0:1].isdigit():
                    try:
                        result.append(int(octal[:3], 8)); i += 4
                    except ValueError:
                        i += 2
                else:
                    i += 2
        else:
            result.append(b[i]); i += 1
    return _pdf_bytes_to_str(bytes(result))


def _decode_pdf_hex_string(b: bytes) -> str:
    hex_clean = re.sub(rb"\s", b"", b)
    if len(hex_clean) % 2:
        hex_clean += b"0"
    try:
        raw = bytes.fromhex(hex_clean.decode("ascii", errors="ignore"))
        return _pdf_bytes_to_str(raw)
    except Exception:
        return ""


def _pdf_bytes_to_str(b: bytes) -> str:
    if len(b) >= 2 and b[:2] in (b"\xfe\xff", b"\xff\xfe"):
        try:
            return b.decode("utf-16")
        except Exception:
            pass
    try:
        return b.decode("latin-1")
    except Exception:
        return b.decode("utf-8", errors="replace")


# ── OCR for image-based PDFs ──────────────────────────────────────────────────

def _apply_ocr(path: str) -> str:
    """
    Apply Tesseract OCR to a PDF by rendering each page to an image first.

    Requires:
      - pytesseract  (pip install pytesseract)
      - Pillow       (pip install Pillow)
      - One of:
          pdf2image  (pip install pdf2image)  + poppler in PATH
          pymupdf    (pip install pymupdf)
    """
    import pytesseract  # type: ignore
    from PIL import Image, ImageFilter, ImageOps  # type: ignore

    images = _pdf_to_images(path)
    if not images:
        raise IOError("Could not render PDF pages to images for OCR.")

    texts: list[str] = []
    for img in images:
        # Preprocess: grayscale → mild sharpening → high contrast
        img = img.convert("L")
        img = img.filter(ImageFilter.SHARPEN)
        img = ImageOps.autocontrast(img)
        text = pytesseract.image_to_string(img, lang="eng+spa")
        if text.strip():
            texts.append(text)

    return "\n\n".join(texts)


def _pdf_to_images(path: str) -> list:
    """
    Render each PDF page to a PIL Image.

    Tries pdf2image first (needs poppler), then pymupdf (fitz).
    Raises ImportError if neither is available.
    """
    # ── pdf2image ────────────────────────────────────────────────────────────
    try:
        from pdf2image import convert_from_path  # type: ignore
        return convert_from_path(path, dpi=200)
    except ImportError:
        pass

    # ── pymupdf (fitz) ───────────────────────────────────────────────────────
    try:
        import fitz  # type: ignore  (pymupdf)
        from PIL import Image
        import io
        doc    = fitz.open(path)
        images = []
        for page in doc:
            pix  = page.get_pixmap(dpi=200)
            data = pix.tobytes("png")
            images.append(Image.open(io.BytesIO(data)))
        return images
    except ImportError:
        pass

    raise ImportError(
        "Cannot render PDF pages for OCR. "
        "Install pdf2image+poppler or pymupdf:  "
        "pip install pdf2image   OR   pip install pymupdf"
    )


# ── DOCX ─────────────────────────────────────────────────────────────────────

def _read_docx(path: str) -> str:
    """Extract plain text from a .docx file using stdlib only."""
    import xml.etree.ElementTree as ET

    WNS    = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    TAG_P  = f"{{{WNS}}}p"
    TAG_T  = f"{{{WNS}}}t"

    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
    except KeyError:
        raise IOError("Invalid .docx file: missing word/document.xml")
    except zipfile.BadZipFile:
        raise IOError("File is not a valid .docx (bad ZIP).")

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

def _read_rtf(path: str) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc, errors="replace") as fh:
                return _rtf_to_text(fh.read())
        except Exception:
            continue
    raise IOError(f"Cannot read '{path}'")


def _rtf_to_text(rtf: str) -> str:
    output: list[str] = []
    i             = 0
    depth         = 0
    ignore_depth: int | None = None
    n             = len(rtf)

    while i < n:
        ch = rtf[i]

        if ch == "{":
            depth += 1; i += 1
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
            depth -= 1; i += 1
            continue

        if ignore_depth is not None:
            i += 1; continue

        if ch == "\\":
            i += 1
            if i >= n: break
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
                if i + 2 < n:
                    try:
                        output.append(chr(int(rtf[i+1:i+3], 16)))
                    except ValueError:
                        pass
                    i += 3
                else:
                    i += 1
            elif nxt == "u":
                j = i + 1
                if j < n and (rtf[j].isdigit() or rtf[j] == "-"):
                    k = j
                    if rtf[k] == "-": k += 1
                    while k < n and rtf[k].isdigit(): k += 1
                    try:
                        cp = int(rtf[j:k])
                        if cp < 0: cp += 65536
                        output.append(chr(cp))
                    except (ValueError, OverflowError):
                        pass
                    i = k
                    if i < n and rtf[i] == " ": i += 1
                else:
                    i += 1
            elif nxt.isalpha() or nxt == "-":
                j = i
                if rtf[j] == "-": j += 1
                while j < n and rtf[j].isalpha(): j += 1
                word = rtf[i:j]
                k = j
                if k < n and (rtf[k].isdigit() or rtf[k] == "-"):
                    while k < n and (rtf[k].isdigit() or rtf[k] == "-"): k += 1
                if k < n and rtf[k] == " ": k += 1

                if   word == "par":       output.append("\n\n")
                elif word == "line":      output.append("\n")
                elif word == "tab":       output.append("\t")
                elif word == "endash":    output.append("–")
                elif word == "emdash":    output.append("—")
                elif word == "lquote":    output.append("\u2018")
                elif word == "rquote":    output.append("\u2019")
                elif word == "ldblquote": output.append("\u201C")
                elif word == "rdblquote": output.append("\u201D")
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
