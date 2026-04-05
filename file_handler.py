# file_handler.py
# Bridge between the UI file-upload flow and the parser module.
# Handles base64-encoded file data sent from the JS side and raw file paths.

from __future__ import annotations

import base64
import os
import tempfile

from parser import extract_text


def handle_file_upload(filename: str, b64_data: str) -> dict:
    """
    Receive a file uploaded from the browser (filename + base64 content),
    write it to a temp file, extract its text, and return the result.

    Returns:
        {"ok": True,  "text": "…extracted text…"}
        {"ok": False, "error": "…message…"}
    """
    try:
        raw = base64.b64decode(b64_data)
    except Exception as exc:
        return {"ok": False, "error": f"Base64 decode error: {exc}"}

    ext = os.path.splitext(filename)[1].lower()
    allowed = {".txt", ".pdf", ".docx", ".rtf"}
    if ext not in allowed:
        return {"ok": False, "error": f"Unsupported file type '{ext}'."}

    # Write to a named temp file so parser can open it by path
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        text = extract_text(tmp_path)
        return {"ok": True, "text": text}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def handle_file_path(path: str) -> dict:
    """
    Extract text from a file specified by its absolute path on disk
    (used when the user drops a file or picks one via the native dialog).

    Returns:
        {"ok": True,  "text": "…"}
        {"ok": False, "error": "…"}
    """
    if not os.path.isfile(path):
        return {"ok": False, "error": f"File not found: '{path}'"}

    try:
        text = extract_text(path)
        return {"ok": True, "text": text}
    except (ValueError, IOError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Unexpected error: {exc}"}
