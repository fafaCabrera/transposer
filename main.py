# main.py
# Entry point for the Chord Transposer desktop application.
# Launches a native PyWebView window — NO console window on any platform.
#
# CLI usage:
#   python main.py                  → open empty app
#   python main.py song.txt         → pre-load a file
#   pythonw main.py song.pdf        → (Windows) no console

from __future__ import annotations

import os
import sys

# ── Suppress console window when launched with python.exe on Windows ──────────
# (PyInstaller --windowed handles packaged builds; this covers dev-mode runs.)
if sys.platform == "win32":
    try:
        import ctypes
        # SW_HIDE = 0
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

import webview

from file_handler import handle_file_upload, handle_file_path, fetch_url
from transposer   import transpose_text
from exporter     import prepare_export


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
        Called once by JS on startup.  Returns the content of the file passed
        as a CLI argument, or {"ok": False} if none was given.
        """
        if len(sys.argv) < 2:
            return {"ok": False, "error": "No file argument."}
        path   = sys.argv[1]
        result = handle_file_path(path)
        if result.get("ok"):
            result["filename"] = os.path.splitext(os.path.basename(path))[0]
            result["path"]     = path
            result["ext"]      = os.path.splitext(path)[1].lower()
        return result

    # ── File handling ────────────────────────────────────────────────────────

    def upload_file(self, filename: str, b64_data: str) -> dict:
        """Receive a file uploaded via the browser widget (base64 encoded)."""
        return handle_file_upload(filename, b64_data)

    def open_file_dialog(self) -> dict:
        """Open a native OS file-picker and return extracted text."""
        file_types = (
            "Supported files (*.txt;*.md;*.pdf;*.docx;*.rtf;*.lnk)",
            "Text / Markdown (*.txt;*.md)",
            "PDF files (*.pdf)",
            "Word documents (*.docx)",
            "Rich Text Format (*.rtf)",
            "Windows Shortcuts (*.lnk)",
            "All files (*.*)",
        )
        picked = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=file_types,
        )
        if not picked:
            return {"ok": False, "error": "No file selected."}
        path   = picked[0]
        result = handle_file_path(path)
        if result.get("ok"):
            result["filename"] = os.path.splitext(os.path.basename(path))[0]
            result["path"]     = path
            result["ext"]      = os.path.splitext(path)[1].lower()
        return result

    # ── URL loading ──────────────────────────────────────────────────────────

    def load_url(self, url: str) -> dict:
        """
        Fetch a URL and extract clean text from the HTML.

        Returns {"ok": True, "text": "…"} or {"ok": False, "error": "…"}.
        """
        return fetch_url(url.strip())

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
            {"ok": False, "error": "…"}
        """
        try:
            lines = transpose_text(
                text,
                semitones = int(semitones),
                notation  = notation,
                use_flats = use_flats,
            )
            return {"ok": True, "lines": lines}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Markdown export ───────────────────────────────────────────────────────

    def export_markdown(
        self,
        raw_text:  str,
        lines:     list,
        song_name: str,
        semitones: int,
        use_flats: bool,
        notation:  str,
    ) -> dict:
        """
        Build the markdown document and open a save-file dialog.

        Returns:
            {"ok": True,  "saved": True, "path": "…"}
            {"ok": True,  "saved": False}            ← user cancelled
            {"ok": False, "error": "…"}
        """
        prep = prepare_export(
            raw_text  = raw_text,
            lines     = lines,
            song_name = song_name or "song",
            semitones = int(semitones),
            use_flats = use_flats,
            notation  = notation,
        )
        if not prep["ok"]:
            return prep

        # Ask user where to save
        save_result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory       = os.path.expanduser("~"),
            save_filename   = prep["filename"],
            file_types      = ("Markdown files (*.md)", "All files (*.*)"),
        )

        if not save_result:
            return {"ok": True, "saved": False}

        # pywebview may return a string or a tuple/list
        save_path = save_result[0] if isinstance(save_result, (list, tuple)) else save_result

        # Ensure .md extension
        if not save_path.lower().endswith(".md"):
            save_path += ".md"

        try:
            with open(save_path, "w", encoding="utf-8") as fh:
                fh.write(prep["content"])
            return {"ok": True, "saved": True, "path": save_path}
        except Exception as exc:
            return {"ok": False, "error": f"Could not write file: {exc}"}

    # ── Direct file save ─────────────────────────────────────────────────────

    def save_file(self, path: str, content: str) -> dict:
        """
        Write `content` directly to `path` (overwrite).
        Used when saving edits back to an already-known .md file.
        """
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_file_dialog(self, content: str, suggested_name: str) -> dict:
        """
        Open a Save-As dialog and write `content` to the chosen path.
        """
        save_result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory     = os.path.expanduser("~"),
            save_filename = suggested_name or "song.md",
            file_types    = ("Markdown files (*.md)", "Text files (*.txt)", "All files (*.*)"),
        )
        if not save_result:
            return {"ok": True, "saved": False}

        path = save_result[0] if isinstance(save_result, (list, tuple)) else save_result
        if not path.lower().endswith((".md", ".txt")):
            path += ".md"

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return {"ok": True, "saved": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Utility ──────────────────────────────────────────────────────────────

    def ping(self) -> str:
        return "pong"


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_ui_path(filename: str) -> str:
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
