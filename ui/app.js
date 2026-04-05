/**
 * app.js — Chord Transposer UI logic
 *
 * Features:
 *  - CLI file pre-load (get_startup_file on init)
 *  - File open dialog + drag-drop + sidebar paste
 *  - Semitone slider with ±1 step buttons
 *  - Notation & accidental toggles
 *  - Chord colour picker + preset swatches
 *  - Font selector
 *  - Zoom in/out controls
 *  - Real-time transposition (debounced)
 *  - Copy to clipboard
 */

"use strict";

// ── Application state ─────────────────────────────────────────────────────────

const state = {
  rawText:      "",          // current source text
  semitones:    0,           // transposition -11…+11
  notation:     "american",  // "american" | "latin"
  accidental:   "sharp",     // "sharp" | "flat"
  chordColor:   "#f9c74f",   // CSS colour for chord highlight
  zoom:         100,         // output font-size percentage (60…220)
  debounceTimer: null,
  initDone:     false,       // guard against double-init
};

// ── DOM helpers ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const els = {
  // Header
  headerFilename:  $("headerFilename"),
  clearBtn:        $("clearBtn"),
  copyBtn:         $("copyBtn"),

  // Import panel
  dropZone:        $("dropZone"),
  fileInput:       $("fileInput"),
  openFileBtn:     $("openFileBtn"),

  // Paste panel
  inputText:       $("inputText"),
  applyTextBtn:    $("applyTextBtn"),

  // Transposition
  slider:          $("transposeSlider"),
  sliderValue:     $("sliderValue"),
  stepDown:        $("stepDown"),
  stepUp:          $("stepUp"),
  resetBtn:        $("resetBtn"),

  // Notation
  notationAm:      $("notationAm"),
  notationLat:     $("notationLat"),
  accSharp:        $("accSharp"),
  accFlat:         $("accFlat"),

  // Appearance
  chordColorPicker: $("chordColorPicker"),
  colorPresets:    $("colorPresets"),
  fontSelect:      $("fontSelect"),
  zoomOut:         $("zoomOut"),
  zoomIn:          $("zoomIn"),
  zoomReset:       $("zoomReset"),
  zoomValue:       $("zoomValue"),

  // Output
  outputContent:   $("outputContent"),
  outputPlaceholder: $("outputPlaceholder"),
};

// ── Bootstrap ─────────────────────────────────────────────────────────────────

// pywebview fires "pywebviewready" when the JS bridge is available.
window.addEventListener("pywebviewready", () => {
  if (!state.initDone) { state.initDone = true; init(); }
});

// Fallback poll — some pywebview builds fire DOMContentLoaded first.
document.addEventListener("DOMContentLoaded", () => {
  const poll = setInterval(() => {
    if (window.pywebview && window.pywebview.api) {
      clearInterval(poll);
      if (!state.initDone) { state.initDone = true; init(); }
    }
  }, 80);
});

async function init() {
  bindPanelHeaders();
  bindFileControls();
  bindPastePanel();
  bindSlider();
  bindStepButtons();
  bindNotationToggle();
  bindAccidentalToggle();
  bindColorPicker();
  bindFontSelector();
  bindZoomControls();
  bindHeaderButtons();
  bindKeyboard();
  applyChordColor(state.chordColor);
  updateSliderLabel();

  // ── Load file passed as CLI argument ──────────────────────────────────────
  try {
    const result = await window.pywebview.api.get_startup_file();
    if (result && result.ok) {
      loadText(result.text, result.filename || "");
      showToast("success", `Loaded: ${result.filename || "file"}`);
    }
  } catch (_) {
    // No CLI argument — that's fine
  }
}

// ── Panel collapse/expand ─────────────────────────────────────────────────────

function bindPanelHeaders() {
  document.querySelectorAll(".panel__header").forEach(header => {
    header.addEventListener("click", () => {
      header.closest(".panel").classList.toggle("collapsed");
    });
  });
}

// ── File controls ─────────────────────────────────────────────────────────────

function bindFileControls() {
  els.openFileBtn.addEventListener("click", openNativeFile);

  els.fileInput.addEventListener("change", async () => {
    const file = els.fileInput.files[0];
    if (file) await readFileObject(file);
    els.fileInput.value = "";
  });

  els.dropZone.addEventListener("click", () => els.fileInput.click());

  els.dropZone.addEventListener("dragover", e => {
    e.preventDefault();
    els.dropZone.classList.add("drag-over");
  });
  els.dropZone.addEventListener("dragleave", () => {
    els.dropZone.classList.remove("drag-over");
  });
  els.dropZone.addEventListener("drop", async e => {
    e.preventDefault();
    els.dropZone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) await readFileObject(file);
  });
}

async function openNativeFile() {
  try {
    const result = await window.pywebview.api.open_file_dialog();
    handleFileResult(result);
  } catch (err) {
    showToast("error", "Could not open file dialog.");
    console.error(err);
  }
}

async function readFileObject(file) {
  const allowed = [".txt", ".pdf", ".docx", ".rtf"];
  const ext = "." + file.name.split(".").pop().toLowerCase();
  if (!allowed.includes(ext)) {
    showToast("error", `Unsupported type: ${ext}`);
    return;
  }
  showToast("info", `Loading ${file.name}…`);
  try {
    const b64    = await fileToBase64(file);
    const result = await window.pywebview.api.upload_file(file.name, b64);
    handleFileResult(result, file.name);
  } catch (err) {
    showToast("error", "Failed to read file.");
    console.error(err);
  }
}

function handleFileResult(result, filename) {
  if (!result || !result.ok) {
    showToast("error", result?.error || "Unknown error.");
    return;
  }
  loadText(result.text, filename || result.filename || "");
  showToast("success", "File loaded.");
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ── Paste panel ───────────────────────────────────────────────────────────────

function bindPastePanel() {
  els.applyTextBtn.addEventListener("click", () => {
    const text = els.inputText.value.trim();
    if (!text) { showToast("error", "Nothing to apply."); return; }
    loadText(text, "");
  });
}

// ── Load text into state + trigger transpose ───────────────────────────────────

function loadText(text, filename) {
  state.rawText            = text;
  els.inputText.value      = text;
  els.headerFilename.textContent = filename || "";
  scheduleTranspose();
}

// ── Header buttons ────────────────────────────────────────────────────────────

function bindHeaderButtons() {
  els.clearBtn.addEventListener("click", () => {
    state.rawText            = "";
    els.inputText.value      = "";
    els.headerFilename.textContent = "";
    renderEmpty();
  });

  els.copyBtn.addEventListener("click", copyOutput);
}

function copyOutput() {
  const text = els.outputContent.textContent || "";
  if (!text.trim()) { showToast("error", "Nothing to copy."); return; }

  if (navigator.clipboard) {
    navigator.clipboard.writeText(text)
      .then(() => showToast("success", "Copied!"))
      .catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = Object.assign(document.createElement("textarea"), {
    value: text,
    style: "position:fixed;opacity:0",
  });
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
  showToast("success", "Copied!");
}

// ── Slider ────────────────────────────────────────────────────────────────────

function bindSlider() {
  els.slider.addEventListener("input", () => {
    state.semitones = parseInt(els.slider.value, 10);
    updateSliderLabel();
    scheduleTranspose();
  });
}

function updateSliderLabel() {
  const v = state.semitones;
  els.sliderValue.textContent = v > 0 ? `+${v}` : String(v);
  els.sliderValue.style.color =
    v > 0 ? "var(--success)" :
    v < 0 ? "var(--danger)"  :
            "var(--accent)";
}

function setSemitones(n) {
  state.semitones  = Math.max(-11, Math.min(11, n));
  els.slider.value = state.semitones;
  updateSliderLabel();
  scheduleTranspose();
}

// ── ±1 step buttons ───────────────────────────────────────────────────────────

function bindStepButtons() {
  els.stepDown.addEventListener("click", () => setSemitones(state.semitones - 1));
  els.stepUp.addEventListener("click",   () => setSemitones(state.semitones + 1));

  els.resetBtn.addEventListener("click", () => setSemitones(0));
}

// ── Notation toggles ──────────────────────────────────────────────────────────

function bindNotationToggle() {
  els.notationAm.addEventListener("click", () => {
    state.notation = "american";
    setActive(els.notationAm, els.notationLat);
    scheduleTranspose();
  });
  els.notationLat.addEventListener("click", () => {
    state.notation = "latin";
    setActive(els.notationLat, els.notationAm);
    scheduleTranspose();
  });
}

function bindAccidentalToggle() {
  els.accSharp.addEventListener("click", () => {
    state.accidental = "sharp";
    setActive(els.accSharp, els.accFlat);
    scheduleTranspose();
  });
  els.accFlat.addEventListener("click", () => {
    state.accidental = "flat";
    setActive(els.accFlat, els.accSharp);
    scheduleTranspose();
  });
}

function setActive(on, off) {
  on.classList.add("active");
  off.classList.remove("active");
}

// ── Chord colour picker ───────────────────────────────────────────────────────

function bindColorPicker() {
  // Live colour input
  els.chordColorPicker.addEventListener("input", e => {
    applyChordColor(e.target.value);
    // Deactivate all swatches when using free picker
    els.colorPresets.querySelectorAll(".color-swatch")
      .forEach(s => s.classList.remove("active"));
  });

  // Preset swatches
  els.colorPresets.querySelectorAll(".color-swatch").forEach(swatch => {
    swatch.addEventListener("click", () => {
      const color = swatch.dataset.color;
      applyChordColor(color);
      els.chordColorPicker.value = color;
      els.colorPresets.querySelectorAll(".color-swatch")
        .forEach(s => s.classList.remove("active"));
      swatch.classList.add("active");
    });
  });
}

function applyChordColor(color) {
  state.chordColor = color;
  document.documentElement.style.setProperty("--chord-color", color);

  // Derive a subtle background from the color (15% opacity equivalent)
  // Using inline alpha trick for broad browser support
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  document.documentElement.style.setProperty(
    "--chord-bg", `rgba(${r},${g},${b},0.13)`
  );
}

// ── Font selector ─────────────────────────────────────────────────────────────

function bindFontSelector() {
  els.fontSelect.addEventListener("change", () => {
    els.outputContent.style.fontFamily = els.fontSelect.value;
  });
}

// ── Zoom controls ─────────────────────────────────────────────────────────────

const ZOOM_STEP = 10;
const ZOOM_MIN  = 60;
const ZOOM_MAX  = 220;

function bindZoomControls() {
  els.zoomOut.addEventListener("click",   () => setZoom(state.zoom - ZOOM_STEP));
  els.zoomIn.addEventListener("click",    () => setZoom(state.zoom + ZOOM_STEP));
  els.zoomReset.addEventListener("click", () => setZoom(100));
}

function setZoom(pct) {
  state.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, pct));
  const px   = (14 * state.zoom / 100).toFixed(1) + "px";
  document.documentElement.style.setProperty("--output-size", px);
  els.zoomValue.textContent = `${state.zoom}%`;
}

// ── Transposition ─────────────────────────────────────────────────────────────

function scheduleTranspose() {
  clearTimeout(state.debounceTimer);
  state.debounceTimer = setTimeout(runTranspose, 120);
}

async function runTranspose() {
  if (!state.rawText.trim()) { renderEmpty(); return; }

  try {
    const result = await window.pywebview.api.transpose(
      state.rawText,
      state.semitones,
      state.notation,
      state.accidental === "flat",
    );

    if (!result || !result.ok) {
      showToast("error", result?.error || "Transposition failed.");
      return;
    }

    renderOutput(result.lines);
  } catch (err) {
    showToast("error", "Communication error.");
    console.error(err);
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function renderOutput(lines) {
  if (!lines || lines.length === 0) { renderEmpty(); return; }

  els.outputPlaceholder.style.display = "none";
  els.outputContent.style.display     = "block";

  const frag = document.createDocumentFragment();

  for (const lineObj of lines) {
    const lineEl = document.createElement("span");
    lineEl.className = "line";

    if (!lineObj.tokens || lineObj.tokens.length === 0) {
      lineEl.appendChild(document.createTextNode("\n"));
    } else {
      for (const token of lineObj.tokens) {
        if (token.type === "chord") {
          const span = document.createElement("span");
          span.className   = "chord";
          span.textContent = token.value;
          span.title       = `Original: ${token.original}`;
          lineEl.appendChild(span);
        } else {
          lineEl.appendChild(document.createTextNode(token.value));
        }
      }
      lineEl.appendChild(document.createTextNode("\n"));
    }

    frag.appendChild(lineEl);
  }

  els.outputContent.innerHTML = "";
  els.outputContent.appendChild(frag);

  // Re-apply font from selector (survives innerHTML wipe)
  if (els.fontSelect.value) {
    els.outputContent.style.fontFamily = els.fontSelect.value;
  }
}

function renderEmpty() {
  els.outputContent.style.display     = "none";
  els.outputPlaceholder.style.display = "flex";
}

// ── Toast notifications ───────────────────────────────────────────────────────

function showToast(type, message) {
  const container = $("toast-container");
  const el = Object.assign(document.createElement("div"), {
    className:   `toast toast--${type}`,
    textContent: message,
  });
  container.appendChild(el);
  setTimeout(() => el.remove(), 3100);
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

function bindKeyboard() {
  document.addEventListener("keydown", e => {
    const inTextarea = document.activeElement === els.inputText;

    // Ctrl/Cmd + O → open file
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o") {
      e.preventDefault();
      openNativeFile();
      return;
    }

    // Ctrl/Cmd + Shift + C → copy output
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "C") {
      e.preventDefault();
      copyOutput();
      return;
    }

    // Ctrl/Cmd + = / - → zoom
    if ((e.ctrlKey || e.metaKey) && (e.key === "=" || e.key === "+")) {
      e.preventDefault();
      setZoom(state.zoom + ZOOM_STEP);
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "-") {
      e.preventDefault();
      setZoom(state.zoom - ZOOM_STEP);
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "0") {
      e.preventDefault();
      setZoom(100);
      return;
    }

    // Arrow keys → change semitones (not while typing)
    if (!inTextarea) {
      if (e.key === "ArrowUp"   || e.key === "ArrowRight") {
        e.preventDefault(); setSemitones(state.semitones + 1);
      }
      if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
        e.preventDefault(); setSemitones(state.semitones - 1);
      }
    }
  });
}
