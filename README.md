# 🎸 LocalChords

A cross-platform desktop application for transposing song lyrics and chord sheets.
Built with **Python + PyWebView** — runs as a native window with no browser required.

---

## Features

### Input
- **Import files** — `.txt`, `.md`, `.pdf`, `.docx`, `.rtf`, `.cho`, `.chopro`, `.lnk`, `.url`
- **ChordPro** — parse `.cho`/`.chopro` files including directives (`{title:}`, `{key:}`, `{start_of_chorus}`, etc.) and inline `[Chord]` markers
- **Drag & drop** — drop any supported file onto the app
- **Paste text** — paste raw chord sheets directly in the sidebar
- **Fetch from URL** — extracts clean chord/lyric text from any webpage
  - Smart extractors for **Ultimate Guitar**, **Cifraclub**, and **lacuerda.net**
  - Generic HTML cleaner fallback for all other sites
- **File Explorer** — browse local folders, open files with a click, sort by name or date
- **Windows shortcuts** — `.lnk` shortcuts are resolved transparently to their target file
- **Internet shortcuts** — `.url` files are resolved to their embedded URL and fetched
- **CLI argument** — pass a file path or URL directly: `python main.py song.cho` or `python main.py https://…`

### Transposition
- **Slider** from −11 to +11 semitones with real-time preview
- **±1 step buttons** and keyboard arrow keys
- **American** notation (C D E F G A B) or **Latin solfège** (Do Re Mi Fa Sol La Si)
- **Sharps ♯** or **Flats ♭** toggle
- Supports all common chord patterns — see [Supported chord formats](#supported-chord-formats)

### Editing
- **Edit mode** — click ✏ Edit to open the source text in an editable textarea
- **Apply** — commits edits back to the source; slider then transposes from the edited text
- **Save** — overwrites the original file (if a path is known) or opens a Save As dialog
- **Dirty indicator** — a `•` appears in the header when there are unsaved edits

### Export
- **Markdown** (`.md`) — with song title, key annotation, and fenced code block
- **ChordPro** (`.cho`) — inline `[Chord]` markers, chord lines merged with lyric lines at correct columns
- **PDF** (`.pdf`) — clean printable document with chords highlighted in your chosen color
- Filenames are auto-named with the detected key: `Song (Key D).md`

### Appearance (all settings persisted across sessions)
- **Chord color** picker with 6 preset swatches
- **Font** selector — JetBrains Mono, Fira Code, Courier New, Consolas, Georgia, Sans-serif
- **Zoom** — 60 % to 220 % in 10 % steps, keyboard shortcuts supported

### Favorites & File Explorer
- **☆ Favorite button** in the header — marks the current file as a favorite
- **Favorites panel** in the sidebar — quick access to all starred files
- **File Explorer panel** — browse any local folder; click files to open them; ☆ to favorite
- Favorites persisted to `~/.localchords/favorites.json`

### Sidebar
- All panels are **collapsible**
- **Drag to reorder** — grab the ⠿ handle and drop panels in any order
- Order persisted in `localStorage` across sessions

### Other
- **Copy to clipboard** — copies the full transposed output
- No console window — behaves like a native GUI app on all platforms
- OCR fallback for image-based / scanned PDFs (requires Tesseract)

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or newer |
| pip | any recent version |

> **Windows**: download Python from https://www.python.org/downloads/
> Make sure to check **"Add Python to PATH"** during installation.

---

## Quick Start

### 1 — Clone the repository

```bash
git clone https://github.com/fafaCabrera/transposer.git
cd transposer
```

### 2 — Create a virtual environment (recommended)

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3 — Install dependencies

**Minimal** (`.txt`, `.docx`, `.rtf`, `.cho`, `.chopro` — no PDF, no URL):
```bash
pip install pywebview
```

**Full install** (all features):
```bash
pip install -r requirements.txt
```

### 4 — Run the app

```bash
# Windows (with console — development)
python main.py

# Windows (no console window — recommended)
pythonw run.pyw

# macOS / Linux
python3 main.py
```

**Pre-load a file or URL on launch:**
```bash
python main.py "My Song.cho"
python main.py "My Song.pdf"
python main.py https://tabs.ultimate-guitar.com/…
```

---

## Dependency Details

### PyWebView (required)

```bash
pip install pywebview
```

Renders the UI inside a native OS window (Edge on Windows, WebKit on macOS, GTK on Linux).

**Linux extra step** — install the GTK WebKit backend:
```bash
# Debian / Ubuntu
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0

# Fedora
sudo dnf install python3-gobject webkit2gtk3
```

---

### PDF text extraction (recommended)

```bash
pip install pdfminer.six
```

Significantly improves extraction quality for text-based PDF chord sheets.
`pypdf` is a lighter alternative: `pip install pypdf`

The app also includes a built-in stdlib extractor (no extra deps) that handles most cases.

---

### OCR — image-based / scanned PDFs (optional)

Some PDFs contain no embedded text (e.g. scanned photos). To handle these:

**Step 1 — Install the Tesseract binary**

| Platform | Command |
|---|---|
| Windows | Download from https://github.com/UB-Mannheim/tesseract/wiki |
| macOS | `brew install tesseract` |
| Debian/Ubuntu | `sudo apt install tesseract-ocr tesseract-ocr-spa` |
| Fedora | `sudo dnf install tesseract` |

> For Spanish songs, install the Spanish language pack:
> `sudo apt install tesseract-ocr-spa`
> Windows: select "Additional language data" during Tesseract setup.

**Step 2 — Install Python packages**

```bash
pip install pytesseract Pillow pymupdf
```

`pymupdf` renders PDF pages to images without any extra binary.
Alternatively use `pdf2image` (requires `poppler` in PATH):
```bash
pip install pdf2image
# Windows poppler: https://github.com/oschwartz10612/poppler-windows/releases
```

---

### URL fetching (optional)

```bash
pip install requests beautifulsoup4
```

Enables the "Fetch from URL" feature. Without these, the app falls back to Python's
built-in `urllib` and a minimal HTML parser — which works for many sites but not all.

---

### PDF export (optional)

```bash
pip install fpdf2
```

Required for the **Export → PDF** feature. Without it, PDF export will show an error
with the install command.

---

### Windows `.lnk` shortcuts (optional)

`.lnk` resolution works out of the box via PowerShell (no extra packages).
If PowerShell is unavailable:

```bash
pip install winshell
```

---

## Building a standalone executable

Requires PyInstaller:

```bash
pip install pyinstaller
```

**One-folder bundle** (recommended — loads fastest):
```bash
python build.py
# Output: dist/LocalChords/
```

**Single-file executable**:
```bash
python build.py --onefile
# Output: dist/LocalChords.exe    (Windows)
#         dist/LocalChords        (Linux)
#         dist/LocalChords.app    (macOS — one-dir only)
```

The packaged app runs without a console window on all platforms.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open file dialog |
| `↑` / `→` | Transpose +1 semitone |
| `↓` / `←` | Transpose −1 semitone |
| `Ctrl+Shift+C` | Copy transposed output |
| `Ctrl+Shift+E` | Export as Markdown |
| `Ctrl++` / `Ctrl+-` | Zoom in / out |
| `Ctrl+0` | Reset zoom |

---

## Supported chord formats

```
C   Cm   C7   Cmaj7   Csus4   Cdim   Caug
C#  Db   Bb   F#m     Cadd9   C9     C11    C13
C/G   Am/E   G7/B              ← slash chords
F#m7(b13)   E7(13)            ← extended / altered
```

Both American (C D E…) and Latin solfège (Do Re Mi…) notation are supported
for input and output.

---

## Supported file formats

| Extension | Description | Notes |
|---|---|---|
| `.txt` `.md` | Plain text / Markdown | Any encoding |
| `.pdf` | PDF documents | Text-based or scanned (OCR) |
| `.docx` | Word documents | Parsed without Microsoft Word |
| `.rtf` | Rich Text Format | Built-in parser |
| `.cho` `.chopro` | ChordPro | Full directive + inline chord support |
| `.lnk` | Windows shortcut | Resolved to target file |
| `.url` | Windows internet shortcut | URL fetched automatically |

---

## Project structure

```
localchords/
├── main.py              # App entry point, PyWebView window + JS↔Python API bridge
├── transposer.py        # Chord regex, detection, transposition engine
├── parser.py            # File text extraction (TXT, PDF, DOCX, RTF, CHO)
├── chordpro_parser.py   # ChordPro directive + inline chord parser
├── file_handler.py      # Upload bridge, .lnk/.url resolver, URL fetcher
├── cleaners.py          # Site-specific HTML extractors (UG, Cifraclub, lacuerda)
├── exporter.py          # Markdown, ChordPro, PDF export builders
├── file_explorer.py     # Folder browsing + favorites persistence
├── state_manager.py     # UI state persistence (zoom, color, font, last folder)
├── build.py             # PyInstaller packaging script
├── run.pyw              # Windows no-console launcher (pythonw double-click)
├── requirements.txt     # Python dependencies
└── ui/
    ├── index.html       # App shell, sidebar panels, output area
    ├── app.js           # All UI logic, Python API calls, state management
    └── styles.css       # Dark theme, layout, component styles
```

### Data stored on disk

| Path | Content |
|---|---|
| `~/.localchords/favorites.json` | Favorited file paths |
| `~/.localchords/ui_state.json` | Last folder, zoom, chord color, font |

---

## License

MIT
