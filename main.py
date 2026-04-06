# main.py
# Entry point for the LocalChords desktop application.
# Launches a native PyWebView window — NO console window on any platform.
#
# CLI usage:
#   python main.py                       → open empty app
#   python main.py song.txt              → pre-load a file
#   python main.py song.cho              → pre-load a ChordPro file
#   python main.py https://tabs.ug/…    → pre-load a URL
#   pythonw main.py song.pdf            → (Windows) no console

from __future__ import annotations

import os
import sys

# ── Suppress console window when launched with python.exe on Windows ──────────
if sys.platform == "win32":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

import webview

from file_handler  import handle_file_upload, handle_file_path, fetch_url
from file_explorer import list_directory, get_favorites, toggle_favorite
from state_manager import load_state, save_state
from transposer    import transpose_text
from exporter      import prepare_export, prepare_chordpro, prepare_pdf


# ── JS ↔ Python API bridge ────────────────────────────────────────────────────

class Api:
    """
    All public methods are callable from JavaScript via
        window.pywebview.api.<method_name>(args)
    Every method must be synchronous and return a JSON-serialisable value.
    """

    # ── Startup file / URL (CLI argument) ────────────────────────────────────

    def get_startup_file(self) -> dict:
        """Called once by JS on startup."""
        if len(sys.argv) < 2:
            return {"ok": False, "error": "No argument."}

        arg = sys.argv[1].strip()

        if arg.startswith(("http://", "https://", "www.")):
            result = fetch_url(arg)
            if result.get("ok"):
                try:
                    from urllib.parse import urlparse
                    host = urlparse(arg if "://" in arg else "https://" + arg).hostname or arg
                    result["filename"] = host
                except Exception:
                    result["filename"] = "url"
            return result

        path   = arg
        result = handle_file_path(path)
        if result.get("ok"):
            result["filename"] = os.path.splitext(os.path.basename(path))[0]
            result["path"]     = path
            result["ext"]      = os.path.splitext(path)[1].lower()
        return result

    # ── File handling ─────────────────────────────────────────────────────────

    def upload_file(self, filename: str, b64_data: str) -> dict:
        """Receive a file uploaded via the browser widget (base64 encoded)."""
        return handle_file_upload(filename, b64_data)

    def open_file_dialog(self) -> dict:
        """Open a native OS file-picker and return extracted text."""
        file_types = (
            "Supported files (*.txt;*.md;*.pdf;*.docx;*.rtf;*.cho;*.chopro;*.lnk;*.url)",
            "Text / Markdown (*.txt;*.md)",
            "ChordPro (*.cho;*.chopro)",
            "PDF files (*.pdf)",
            "Word documents (*.docx)",
            "Rich Text Format (*.rtf)",
            "Windows Shortcuts (*.lnk;*.url)",
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

    def open_file_by_path(self, path: str) -> dict:
        """Open a file by its full path (from file explorer, without dialog)."""
        result = handle_file_path(path)
        if result.get("ok"):
            result["filename"] = os.path.splitext(os.path.basename(path))[0]
            result["path"]     = path
            result["ext"]      = os.path.splitext(path)[1].lower()
        return result

    # ── URL loading ───────────────────────────────────────────────────────────

    def load_url(self, url: str) -> dict:
        """Fetch a URL and extract clean text from the HTML."""
        return fetch_url(url.strip())

    # ── File Explorer ─────────────────────────────────────────────────────────

    def open_folder_dialog(self) -> dict:
        """Open a native folder picker dialog."""
        picked = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG,
        )
        if not picked:
            return {"ok": False, "error": "No folder selected."}
        path   = picked[0] if isinstance(picked, (list, tuple)) else picked
        result = list_directory(path)
        if result.get("ok"):
            save_state({"last_folder": path})
        return result

    def browse_folder(self, path: str) -> dict:
        """List supported files in *path*."""
        result = list_directory(path)
        if result.get("ok"):
            save_state({"last_folder": path})
        return result

    def get_favorites(self) -> dict:
        return get_favorites()

    def toggle_favorite(self, path: str) -> dict:
        return toggle_favorite(path)

    # ── UI state ──────────────────────────────────────────────────────────────

    def get_ui_state(self) -> dict:
        return {"ok": True, **load_state()}

    def save_ui_state(self, updates: dict) -> dict:
        return save_state(updates)

    # ── Transposition ─────────────────────────────────────────────────────────

    def transpose(
        self,
        text:      str,
        semitones: int,
        notation:  str  = "american",
        use_flats: bool = False,
    ) -> dict:
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
        return self._save_dialog_text(
            prep["content"], prep["filename"],
            ("Markdown files (*.md)", "All files (*.*)"),
        )

    # ── ChordPro export ───────────────────────────────────────────────────────

    def export_chordpro(
        self,
        raw_text:  str,
        lines:     list,
        song_name: str,
        semitones: int,
        use_flats: bool,
        notation:  str,
    ) -> dict:
        prep = prepare_chordpro(
            raw_text  = raw_text,
            lines     = lines,
            song_name = song_name or "song",
            semitones = int(semitones),
            use_flats = use_flats,
            notation  = notation,
        )
        if not prep["ok"]:
            return prep
        return self._save_dialog_text(
            prep["content"], prep["filename"],
            ("ChordPro files (*.cho;*.chopro)", "All files (*.*)"),
        )

    # ── PDF export ────────────────────────────────────────────────────────────

    def export_pdf(
        self,
        raw_text:    str,
        lines:       list,
        song_name:   str,
        semitones:   int,
        use_flats:   bool,
        notation:    str,
        chord_color: str = "#f9a825",
    ) -> dict:
        prep = prepare_pdf(
            raw_text    = raw_text,
            lines       = lines,
            song_name   = song_name or "song",
            semitones   = int(semitones),
            use_flats   = use_flats,
            notation    = notation,
            chord_color = chord_color,
        )
        if not prep["ok"]:
            return prep
        return self._save_dialog_bytes(
            prep["bytes"], prep["filename"],
            ("PDF files (*.pdf)", "All files (*.*)"),
        )

    # ── Direct file save ──────────────────────────────────────────────────────

    def save_file(self, path: str, content: str) -> dict:
        """Write `content` directly to `path` (overwrite)."""
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_file_dialog(self, content: str, suggested_name: str) -> dict:
        """Open a Save-As dialog and write `content` to the chosen path."""
        return self._save_dialog_text(
            content,
            suggested_name or "song.md",
            ("Markdown files (*.md)", "Text files (*.txt)", "All files (*.*)"),
        )

    # ── Utility ───────────────────────────────────────────────────────────────

    def ping(self) -> str:
        return "pong"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _save_dialog_text(
        self, content: str, filename: str, file_types: tuple
    ) -> dict:
        save_result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory     = os.path.expanduser("~"),
            save_filename = filename,
            file_types    = file_types,
        )
        if not save_result:
            return {"ok": True, "saved": False}

        path = save_result[0] if isinstance(save_result, (list, tuple)) else save_result
        _, sug_ext    = os.path.splitext(filename)
        _, chosen_ext = os.path.splitext(path)
        if not chosen_ext and sug_ext:
            path += sug_ext

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return {"ok": True, "saved": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": f"Could not write file: {exc}"}

    def _save_dialog_bytes(
        self, data: bytes, filename: str, file_types: tuple
    ) -> dict:
        save_result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory     = os.path.expanduser("~"),
            save_filename = filename,
            file_types    = file_types,
        )
        if not save_result:
            return {"ok": True, "saved": False}

        path = save_result[0] if isinstance(save_result, (list, tuple)) else save_result
        _, sug_ext    = os.path.splitext(filename)
        _, chosen_ext = os.path.splitext(path)
        if not chosen_ext and sug_ext:
            path += sug_ext

        try:
            with open(path, "wb") as fh:
                fh.write(data)
            return {"ok": True, "saved": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": f"Could not write file: {exc}"}


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
        title     = "LocalChords",
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
