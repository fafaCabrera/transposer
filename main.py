# main.py
# Entry point for the Chord Transposer desktop application.
# Launches a native PyWebView window that hosts the HTML/CSS/JS UI.
# Python ↔ JS communication is handled via the Api class (JS bridge).
#
# CLI usage:
#   python main.py                  → open empty app
#   python main.py song.txt         → open and pre-load a file
#   python main.py song.pdf         → same for any supported format

from __future__ import annotations

import os
import sys

import webview

from file_handler import handle_file_upload, handle_file_path
from transposer   import transpose_text


# ── JS ↔ Python API bridge ───────────────────────────────────────────────────

class Api:
    """
    All public methods are callable from JavaScript via
        window.pywebview.api.<method_name>(args)
    Every method must be synchronous and return a JSON-serialisable value.
    """

    # ── Startup file (CLI argument) ──────────────────────────────────────────

    def get_startup_file(self) -> dict:
        """
        Called once by JS on startup.
        If the app was launched with a file path argument, extract and return
        its text so the UI can pre-load it automatically.

        Returns:
            {"ok": True,  "text": "...", "filename": "..."}
            {"ok": False, "error": "..."}   ← no arg or error
        """
        if len(sys.argv) < 2:
            return {"ok": False, "error": "No file argument provided."}

        path = sys.argv[1]
        result = handle_file_path(path)
        if result["ok"]:
            result["filename"] = os.path.basename(path)
        return result

    # ── File handling ────────────────────────────────────────────────────────

    def upload_file(self, filename: str, b64_data: str) -> dict:
        """
        Called when the user uploads a file through the browser widget.
        `b64_data` is the file's binary content encoded in base64.
        """
        return handle_file_upload(filename, b64_data)

    def open_file_dialog(self) -> dict:
        """
        Open a native OS file-picker dialog and extract text from the chosen
        file. Returns the same dict shape as upload_file().
        """
        file_types = (
            "Supported files (*.txt;*.pdf;*.docx;*.rtf)",
            "Text files (*.txt)",
            "PDF files (*.pdf)",
            "Word documents (*.docx)",
            "Rich Text Format (*.rtf)",
            "All files (*.*)",
        )
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=file_types,
        )
        if not result:
            return {"ok": False, "error": "No file selected."}

        path   = result[0]
        result = handle_file_path(path)
        if result.get("ok"):
            result["filename"] = os.path.basename(path)
        return result

    # ── Transposition ────────────────────────────────────────────────────────

    def transpose(
        self,
        text:      str,
        semitones: int,
        notation:  str  = "american",
        use_flats: bool = False,
    ) -> dict:
        """
        Transpose all chords in `text` by `semitones` steps.

        Returns:
            {"ok": True,  "lines": [ {"original": str, "tokens": [...]} ]}
            {"ok": False, "error": "..."}
        """
        try:
            semitones = int(semitones)
            lines = transpose_text(
                text,
                semitones = semitones,
                notation  = notation,
                use_flats = use_flats,
            )
            return {"ok": True, "lines": lines}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Utility ──────────────────────────────────────────────────────────────

    def ping(self) -> str:
        """Health-check called by JS on startup."""
        return "pong"


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_ui_path(filename: str) -> str:
    """
    Resolve path to a UI file whether running from source or from a
    PyInstaller one-file bundle (_MEIPASS is set in the latter case).
    """
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS          # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "ui", filename)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    api        = Api()
    index_path = resolve_ui_path("index.html")

    webview.create_window(
        title     = "Chord Transposer",
        url       = index_path,
        js_api    = api,
        width     = 1000,
        height    = 720,
        min_size  = (640, 480),
        resizable = True,
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()
