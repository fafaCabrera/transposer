# 🎸 Chord Transposer

A cross-platform desktop application for transposing song lyrics and chord sheets.
Built with Python + PyWebView — runs as a native window, no browser required.

![screenshot placeholder](https://raw.githubusercontent.com/fafaCabrera/transposer/master/docs/screenshot.png)

---

## Features

- **Transpose** chords −11 to +11 semitones with a slider or ±1 step buttons
- **Import** files: `.txt`, `.pdf`, `.docx`, `.rtf`, Windows `.lnk` shortcuts
- **Fetch from URL** — extracts clean text from any chord/lyric webpage
- **OCR** fallback for image-based PDFs (requires Tesseract)
- **Export to Markdown** — auto-detects key for smart filenames (`song (Key D).md`)
- **Notation** toggle: American (C D E…) ↔ Latin solfège (Do Re Mi…)
- **Accidentals** toggle: ♯ Sharps ↔ ♭ Flats
- **Chord colour** picker with presets
- **Font** selector and zoom controls
- No console window — behaves like a native GUI app

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or newer |
| pip | any recent version |

> **Windows users**: if you don't have Python installed, download it from
> https://www.python.org/downloads/ — make sure to check **"Add Python to PATH"**.

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

**Minimal install** (basic `.txt` / `.docx` / `.rtf` support):
```bash
pip install pywebview
```

**Full install** (PDF extraction + URL fetching + OCR):
```bash
pip install -r requirements.txt
```

### 4 — Run the app

```bash
# Windows (with console)
python main.py

# Windows (no console window — recommended)
pythonw run.pyw

# macOS / Linux
python3 main.py
```

You can also pass a file to open it immediately:
```bash
python main.py "My Song.txt"
python main.py "song.pdf"
```

---

## Dependency Details

### PyWebView (required)

```bash
pip install pywebview
```

Renders the UI inside a native OS window (Edge on Windows, WebKit on macOS/Linux).

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

This improves PDF support significantly for most text-based PDF chord sheets.
`pypdf` is a lighter alternative: `pip install pypdf`

---

### OCR — image-based PDFs (optional)

Some PDFs are scanned images with no embedded text. To handle these:

**Step 1 — Install Tesseract binary**

| Platform | Command |
|---|---|
| Windows | Download installer from https://github.com/UB-Mannheim/tesseract/wiki |
| macOS | `brew install tesseract` |
| Debian/Ubuntu | `sudo apt install tesseract-ocr tesseract-ocr-spa` |
| Fedora | `sudo dnf install tesseract` |

> For Spanish songs, also install the Spanish language pack:
> `sudo apt install tesseract-ocr-spa`
> Windows: select "Additional language data" during Tesseract setup.

**Step 2 — Install Python packages**

```bash
pip install pytesseract Pillow pymupdf
```

`pymupdf` renders PDF pages to images without any extra binary.
Alternatively, use `pdf2image` (requires `poppler` in PATH):
```bash
pip install pdf2image
# Windows poppler: https://github.com/oschwartz10612/poppler-windows/releases
```

---

### URL fetching (optional)

```bash
pip install requests beautifulsoup4
```

Enables the "Fetch from URL" feature. Falls back to Python's built-in `urllib`
and a minimal HTML parser if these are not installed.

---

### Windows .lnk shortcuts (optional)

`.lnk` resolution works out of the box via PowerShell on Windows.
If you need it without PowerShell:
```bash
pip install winshell
```

---

## Building a standalone executable

Requires PyInstaller:

```bash
pip install pyinstaller
```

**One-folder bundle** (loads fastest):
```bash
python build.py
# Output: dist/ChordTransposer/
```

**Single-file executable**:
```bash
python build.py --onefile
# Output: dist/ChordTransposer.exe   (Windows)
#         dist/ChordTransposer       (Linux)
#         dist/ChordTransposer.app   (macOS)
```

The packaged app runs without a console window on all platforms.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open file dialog |
| `↑` / `↓` | Transpose +1 / −1 semitone |
| `Ctrl+Shift+C` | Copy transposed output |
| `Ctrl+Shift+E` | Export as Markdown |
| `Ctrl++` / `Ctrl+-` | Zoom in / out |
| `Ctrl+0` | Reset zoom |

---

## Supported chord formats

```
C   Cm   C7   Cmaj7   Csus4   Cdim   Caug
C#  Db   Bb   F#m     Cadd9   C9     C11    C13
C/G  Am/E  G7/B            ← slash chords
F#m7(b13)  E7(13)          ← extended / altered
```

---

## Project structure

```
transposer/
├── main.py          # App entry point, PyWebView window + JS bridge
├── transposer.py    # Chord detection & transposition engine
├── parser.py        # File text extraction (TXT, PDF, DOCX, RTF, OCR)
├── file_handler.py  # Upload bridge, .lnk resolver, URL fetcher
├── exporter.py      # Markdown export builder
├── build.py         # PyInstaller packaging script
├── run.pyw          # Windows no-console launcher (double-click)
├── requirements.txt # Python dependencies
└── ui/
    ├── index.html   # App shell & controls
    ├── app.js       # UI logic & Python bridge calls
    └── styles.css   # Dark theme styles
```

---

## License

MIT
