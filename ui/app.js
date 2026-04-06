/**
 * app.js — LocalChords UI logic
 */

"use strict";

// ── Application state ─────────────────────────────────────────────────────────

const state = {
  rawText:         "",          // current source text (always the editable base)
  songName:        "",          // filename without extension
  filePath:        "",          // full path of loaded file (if known)
  fileExt:         "",          // extension e.g. ".md"
  semitones:       0,
  notation:        "american",
  accidental:      "sharp",
  chordColor:      "#f9c74f",
  zoom:            100,
  lastLines:       [],          // most recent tokenised lines from Python
  isEditing:       false,
  isDirty:         false,       // unsaved edits
  debounceTimer:   null,
  initDone:        false,
  explorerPath:    "",
  explorerSort:    "name",
  explorerEntries: [],
};

// ── DOM helpers ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const els = {
  // Header
  headerFilename:   $("headerFilename"),
  clearBtn:         $("clearBtn"),
  editBtn:          $("editBtn"),
  exportBtn:        $("exportBtn"),
  copyBtn:          $("copyBtn"),

  // Import panel
  dropZone:         $("dropZone"),
  fileInput:        $("fileInput"),
  openFileBtn:      $("openFileBtn"),
  urlInput:         $("urlInput"),
  urlFetchBtn:      $("urlFetchBtn"),

  // Paste panel
  inputText:        $("inputText"),
  applyTextBtn:     $("applyTextBtn"),

  // Transposition
  slider:           $("transposeSlider"),
  sliderValue:      $("sliderValue"),
  stepDown:         $("stepDown"),
  stepUp:           $("stepUp"),
  resetBtn:         $("resetBtn"),

  // Notation
  notationAm:       $("notationAm"),
  notationLat:      $("notationLat"),
  accSharp:         $("accSharp"),
  accFlat:          $("accFlat"),

  // Appearance
  chordColorPicker: $("chordColorPicker"),
  colorPresets:     $("colorPresets"),
  fontSelect:       $("fontSelect"),
  zoomOut:          $("zoomOut"),
  zoomIn:           $("zoomIn"),
  zoomReset:        $("zoomReset"),
  zoomValue:        $("zoomValue"),

  // Export panel
  exportMdBtn:      $("exportMdBtn"),
  exportChoBtn:     $("exportChoBtn"),
  exportPdfBtn:     $("exportPdfBtn"),

  // Output
  outputContent:    $("outputContent"),
  outputPlaceholder: $("outputPlaceholder"),
  editBar:          $("editBar"),
  editTextarea:     $("editTextarea"),
  applyEditBtn:     $("applyEditBtn"),
  saveEditBtn:      $("saveEditBtn"),
  cancelEditBtn:    $("cancelEditBtn"),

  // Loading overlay
  loadingOverlay:   $("loadingOverlay"),
  loadingMsg:       $("loadingMsg"),
};

// ── Bootstrap ─────────────────────────────────────────────────────────────────

window.addEventListener("pywebviewready", () => {
  if (!state.initDone) { state.initDone = true; init(); }
});

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
  bindUrlFetch();
  bindPastePanel();
  bindSlider();
  bindStepButtons();
  bindNotationToggle();
  bindAccidentalToggle();
  bindColorPicker();
  bindFontSelector();
  bindZoomControls();
  bindHeaderButtons();
  bindExportPanel();
  bindEditBar();
  bindFileExplorer();
  bindFavorites();
  initSidebarDragDrop();
  bindKeyboard();

  applyChordColor(state.chordColor);
  updateSliderLabel();

  // Load file/URL passed as CLI argument
  try {
    const result = await window.pywebview.api.get_startup_file();
    if (result && result.ok) {
      loadText(result.text, result.filename || "", result.path || "", result.ext || "", result.meta);
      showToast("success", `Loaded: ${result.filename || "file"}`);
    }
  } catch (_) { /* no CLI arg — normal */ }
}

// ── Panel collapse / expand ───────────────────────────────────────────────────

function bindPanelHeaders() {
  document.querySelectorAll(".panel__header").forEach(header => {
    header.addEventListener("click", e => {
      // Don't toggle collapse when clicking the drag handle
      if (e.target.closest(".drag-handle")) return;
      header.closest(".panel").classList.toggle("collapsed");
    });
  });
}

// ── Sidebar drag-and-drop reorder ────────────────────────────────────────────

function initSidebarDragDrop() {
  const sidebar = document.querySelector(".sidebar");
  let dragPanel = null;

  sidebar.addEventListener("dragstart", e => {
    const panel = e.target.closest(".panel");
    if (!panel) return;
    dragPanel = panel;
    panel.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
  });

  sidebar.addEventListener("dragend", () => {
    if (dragPanel) {
      dragPanel.classList.remove("dragging");
      dragPanel = null;
    }
    sidebar.querySelectorAll(".panel.drag-over")
      .forEach(p => p.classList.remove("drag-over"));
    saveSidebarOrder();
  });

  sidebar.addEventListener("dragover", e => {
    e.preventDefault();
    if (!dragPanel) return;
    const target = e.target.closest(".panel");
    if (!target || target === dragPanel) return;
    sidebar.querySelectorAll(".panel.drag-over")
      .forEach(p => p.classList.remove("drag-over"));
    target.classList.add("drag-over");
    const rect = target.getBoundingClientRect();
    if (e.clientY < rect.top + rect.height / 2) {
      sidebar.insertBefore(dragPanel, target);
    } else {
      sidebar.insertBefore(dragPanel, target.nextSibling);
    }
  });

  sidebar.addEventListener("dragleave", e => {
    const target = e.target.closest(".panel");
    if (target) target.classList.remove("drag-over");
  });

  sidebar.addEventListener("drop", e => e.preventDefault());

  loadSidebarOrder();
}

function saveSidebarOrder() {
  const order = [...document.querySelectorAll(".sidebar .panel")]
    .map(p => p.dataset.panelId).filter(Boolean);
  try { localStorage.setItem("lc_sidebar_order", JSON.stringify(order)); } catch (_) {}
}

function loadSidebarOrder() {
  try {
    const saved = JSON.parse(localStorage.getItem("lc_sidebar_order") || "[]");
    if (!saved.length) return;
    const sidebar = document.querySelector(".sidebar");
    for (const id of saved) {
      const panel = sidebar.querySelector(`[data-panel-id="${id}"]`);
      if (panel) sidebar.appendChild(panel);
    }
  } catch (_) {}
}

// ── File import controls ──────────────────────────────────────────────────────

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
  const allowed = [".txt", ".md", ".pdf", ".docx", ".rtf", ".cho", ".chopro", ".url", ".lnk"];
  const ext = "." + file.name.split(".").pop().toLowerCase();
  if (!allowed.includes(ext)) {
    showToast("error", `Unsupported type: ${ext}`);
    return;
  }

  if (ext === ".pdf") showLoading("Extracting PDF…");
  else                showLoading(`Loading ${file.name}…`);

  try {
    const b64    = await fileToBase64(file);
    const result = await window.pywebview.api.upload_file(file.name, b64);
    handleFileResult(result, stripExt(file.name));
  } catch (err) {
    showToast("error", "Failed to read file.");
    console.error(err);
  } finally {
    hideLoading();
  }
}

function handleFileResult(result, nameHint) {
  if (!result || !result.ok) {
    showToast("error", result?.error || "Unknown error.");
    return;
  }
  const meta = result.meta || null;
  const name = (meta && meta.title) || nameHint || result.filename || "";
  loadText(result.text, name, result.path || "", result.ext || "", meta);
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

// ── URL fetch ─────────────────────────────────────────────────────────────────

function bindUrlFetch() {
  const doFetch = () => {
    const url = els.urlInput.value.trim();
    if (url) fetchFromUrl(url);
  };
  els.urlFetchBtn.addEventListener("click", doFetch);
  els.urlInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); doFetch(); }
  });
}

async function fetchFromUrl(url) {
  showLoading("Fetching URL…");
  try {
    const result = await window.pywebview.api.load_url(url);
    if (!result || !result.ok) {
      showToast("error", result?.error || "Failed to fetch URL.");
      return;
    }
    let name = "";
    try { name = new URL(url.startsWith("http") ? url : "https://" + url).hostname; }
    catch (_) { name = "url"; }
    loadText(result.text, name);
    showToast("success", "URL content loaded.");
  } catch (err) {
    showToast("error", "Could not reach URL.");
    console.error(err);
  } finally {
    hideLoading();
  }
}

// ── Paste panel ───────────────────────────────────────────────────────────────

function bindPastePanel() {
  els.applyTextBtn.addEventListener("click", () => {
    const text = els.inputText.value.trim();
    if (!text) { showToast("error", "Nothing to apply."); return; }
    loadText(text, "");
  });
}

// ── Load text → state ─────────────────────────────────────────────────────────

function loadText(text, name, path, ext, meta) {
  state.rawText  = text;
  state.songName = (meta && meta.title) || name || "";
  state.filePath = path || "";
  state.fileExt  = ext  || "";
  state.isDirty  = false;
  els.inputText.value = text;
  updateDirtyIndicator();
  exitEditMode();
  scheduleTranspose();
}

// ── Dirty state ───────────────────────────────────────────────────────────────

function updateDirtyIndicator() {
  const name = state.songName || "";
  els.headerFilename.textContent = name + (state.isDirty ? " •" : "");
}

// ── Header buttons ────────────────────────────────────────────────────────────

function bindHeaderButtons() {
  els.clearBtn.addEventListener("click", () => {
    state.rawText   = "";
    state.songName  = "";
    state.filePath  = "";
    state.fileExt   = "";
    state.lastLines = [];
    state.isDirty   = false;
    els.inputText.value = "";
    updateDirtyIndicator();
    exitEditMode();
    renderEmpty();
  });

  els.editBtn.addEventListener("click", () => {
    state.isEditing ? exitEditMode() : enterEditMode();
  });

  els.copyBtn.addEventListener("click",   copyOutput);
  els.exportBtn.addEventListener("click", exportMarkdown);
}

// ── Edit bar ──────────────────────────────────────────────────────────────────

function bindEditBar() {
  els.applyEditBtn.addEventListener("click",  applyEdit);
  els.saveEditBtn.addEventListener("click",   saveEdit);
  els.cancelEditBtn.addEventListener("click", exitEditMode);

  // Track edits → dirty state
  els.editTextarea.addEventListener("input", () => {
    if (state.isEditing) {
      state.isDirty = true;
      updateDirtyIndicator();
    }
  });
}

// ── Edit mode ─────────────────────────────────────────────────────────────────

function enterEditMode() {
  if (!state.rawText.trim()) { showToast("error", "Nothing to edit."); return; }
  state.isEditing = true;

  // Show the RAW source text (not the transposed output)
  els.editTextarea.value = state.rawText;

  els.outputContent.style.display  = "none";
  els.editTextarea.style.display   = "block";
  els.editBar.style.display        = "flex";
  $("outputScroll").classList.add("editing");

  els.editBtn.textContent = "👁 View";
  els.editBtn.title       = "Switch back to view mode";
  els.saveEditBtn.textContent = state.filePath ? "💾 Save" : "💾 Save As…";

  els.editTextarea.focus();
}

function exitEditMode() {
  if (!state.isEditing) return;
  state.isEditing = false;

  els.editTextarea.style.display  = "none";
  els.editBar.style.display       = "none";
  els.outputContent.style.display = state.lastLines.length ? "block" : "none";
  $("outputScroll").classList.remove("editing");

  els.editBtn.textContent = "✏ Edit";
  els.editBtn.title       = "Edit source";
}

async function applyEdit() {
  const content = els.editTextarea.value;
  if (!content.trim()) { showToast("error", "Nothing to apply."); return; }

  // Persist edited text as the new source
  state.rawText = content;
  state.isDirty = false;
  updateDirtyIndicator();
  exitEditMode();
  scheduleTranspose();
  showToast("success", "Applied — re-transposing from edited text.");
}

async function saveEdit() {
  const content = els.editTextarea.value;
  if (!content.trim()) { showToast("error", "Nothing to save."); return; }

  showLoading("Saving…");
  try {
    let result;
    if (state.filePath) {
      result = await window.pywebview.api.save_file(state.filePath, content);
      if (result.ok) {
        state.rawText = content;
        state.isDirty = false;
        updateDirtyIndicator();
        showToast("success", `Saved: ${state.filePath.split(/[/\\]/).pop()}`);
        exitEditMode();
        scheduleTranspose();
      } else {
        showToast("error", result.error || "Save failed.");
      }
    } else {
      const suggested = state.songName ? `${state.songName}.md` : "song.md";
      result = await window.pywebview.api.save_file_dialog(content, suggested);
      if (!result.ok) { showToast("error", result.error || "Save failed."); return; }
      if (result.saved) {
        state.rawText  = content;
        state.filePath = result.path;
        state.fileExt  = ".md";
        state.isDirty  = false;
        updateDirtyIndicator();
        showToast("success", `Saved: ${result.path.split(/[/\\]/).pop()}`);
        exitEditMode();
        scheduleTranspose();
      } else {
        showToast("info", "Save cancelled.");
      }
    }
  } catch (err) {
    showToast("error", "Save error."); console.error(err);
  } finally {
    hideLoading();
  }
}

function copyOutput() {
  const text = els.outputContent.textContent || "";
  if (!text.trim()) { showToast("error", "Nothing to copy."); return; }
  const write = txt =>
    navigator.clipboard
      ? navigator.clipboard.writeText(txt)
          .then(() => showToast("success", "Copied!"))
          .catch(() => fallbackCopy(txt))
      : fallbackCopy(txt);
  write(text);
}

function fallbackCopy(text) {
  const ta = Object.assign(document.createElement("textarea"), {
    value: text, style: "position:fixed;opacity:0",
  });
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
  showToast("success", "Copied!");
}

// ── File Explorer ─────────────────────────────────────────────────────────────

function bindFileExplorer() {
  $("openFolderBtn").addEventListener("click", openExplorerFolder);
  $("sortByName").addEventListener("click", () => setExplorerSort("name"));
  $("sortByDate").addEventListener("click", () => setExplorerSort("date"));

  // Restore last folder from persisted state
  window.pywebview.api.get_ui_state().then(st => {
    if (st && st.last_folder) {
      state.explorerPath = st.last_folder;
      refreshExplorer();
    }
  }).catch(() => {});
}

async function openExplorerFolder() {
  showLoading("Opening folder…");
  try {
    const result = await window.pywebview.api.open_folder_dialog();
    if (!result.ok) {
      showToast("error", result.error || "No folder selected.");
      return;
    }
    state.explorerPath    = result.path;
    state.explorerEntries = result.entries || [];
    renderExplorer();
  } catch (err) {
    showToast("error", "Could not open folder."); console.error(err);
  } finally {
    hideLoading();
  }
}

async function refreshExplorer() {
  if (!state.explorerPath) return;
  try {
    const result = await window.pywebview.api.browse_folder(state.explorerPath);
    if (result.ok) {
      state.explorerEntries = result.entries || [];
      renderExplorer();
    }
  } catch (_) {}
}

function setExplorerSort(mode) {
  state.explorerSort = mode;
  $("sortByName").classList.toggle("active", mode === "name");
  $("sortByDate").classList.toggle("active", mode === "date");
  renderExplorer();
}

function renderExplorer() {
  const list   = $("explorerList");
  const pathEl = $("explorerPath");

  pathEl.textContent = state.explorerPath
    ? (state.explorerPath.split(/[/\\]/).pop() || state.explorerPath)
    : "No folder selected";
  pathEl.title = state.explorerPath;

  let entries = [...state.explorerEntries];
  if (state.explorerSort === "date") {
    entries.sort((a, b) => b.modified - a.modified);
  } else {
    entries.sort((a, b) => a.name.localeCompare(b.name));
  }

  if (!entries.length) {
    list.innerHTML = '<span class="explorer-empty">No supported files in this folder</span>';
    return;
  }

  list.innerHTML = "";
  for (const entry of entries) {
    list.appendChild(makeFileEntry(entry));
  }
}

function makeFileEntry(entry) {
  const div = document.createElement("div");
  div.className = "file-entry";

  const icon = document.createElement("span");
  icon.className   = "file-entry__icon";
  icon.textContent = extIcon(entry.ext);

  const name = document.createElement("span");
  name.className   = "file-entry__name";
  name.textContent = entry.name;
  name.title       = entry.path;
  name.addEventListener("click", () => openFileFromExplorer(entry));

  const favBtn = document.createElement("button");
  favBtn.className   = "fav-btn" + (entry.is_favorite ? " active" : "");
  favBtn.textContent = entry.is_favorite ? "⭐" : "☆";
  favBtn.title       = entry.is_favorite ? "Remove from favorites" : "Add to favorites";
  favBtn.addEventListener("click", e => {
    e.stopPropagation();
    toggleFavorite(entry.path);
  });

  div.appendChild(icon);
  div.appendChild(name);
  div.appendChild(favBtn);
  return div;
}

function extIcon(ext) {
  const map = {
    '.pdf':    '📕', '.docx':   '📘', '.txt':    '📄',
    '.md':     '📝', '.cho':    '🎵', '.chopro': '🎵',
    '.url':    '🌐', '.lnk':   '🔗', '.rtf':    '📄',
  };
  return map[ext] || '📄';
}

async function openFileFromExplorer(entry) {
  showLoading(`Loading ${entry.name}…`);
  try {
    const result = await window.pywebview.api.open_file_by_path(entry.path);
    handleFileResult(result, entry.stem);
  } catch (err) {
    showToast("error", "Could not open file."); console.error(err);
  } finally {
    hideLoading();
  }
}

// ── Favorites ─────────────────────────────────────────────────────────────────

function bindFavorites() {
  refreshFavorites();
}

async function refreshFavorites() {
  try {
    const result = await window.pywebview.api.get_favorites();
    if (result.ok) renderFavorites(result.favorites);
  } catch (_) {}
}

function renderFavorites(favs) {
  const list = $("favoritesList");
  if (!favs || !favs.length) {
    list.innerHTML = '<span class="explorer-empty">No favorites yet — ☆ a file to add it</span>';
    return;
  }
  list.innerHTML = "";
  for (const fav of favs) {
    list.appendChild(makeFileEntry({ ...fav, is_favorite: true }));
  }
}

async function toggleFavorite(path) {
  try {
    const result = await window.pywebview.api.toggle_favorite(path);
    if (!result.ok) { showToast("error", result.error || "Failed."); return; }
    // Sync explorer entries
    state.explorerEntries = state.explorerEntries.map(e =>
      e.path === path ? { ...e, is_favorite: result.is_favorite } : e
    );
    renderExplorer();
    renderFavorites(result.favorites);
    showToast(
      result.is_favorite ? "success" : "info",
      result.is_favorite ? "Added to favorites" : "Removed from favorites",
    );
  } catch (err) {
    showToast("error", "Favorites error."); console.error(err);
  }
}

// ── Export functions ──────────────────────────────────────────────────────────

function bindExportPanel() {
  els.exportMdBtn.addEventListener("click",  exportMarkdown);
  els.exportChoBtn.addEventListener("click", exportChordPro);
  els.exportPdfBtn.addEventListener("click", exportPDF);
}

function _exportArgs() {
  return [
    state.rawText,
    state.lastLines,
    state.songName || "song",
    state.semitones,
    state.accidental === "flat",
    state.notation,
  ];
}

async function exportMarkdown() {
  if (!state.rawText.trim())   { showToast("error", "Nothing to export."); return; }
  if (!state.lastLines.length) { showToast("error", "Transpose first.");   return; }
  showLoading("Preparing Markdown…");
  try {
    const result = await window.pywebview.api.export_markdown(..._exportArgs());
    _handleExportResult(result);
  } catch (err) {
    showToast("error", "Export error."); console.error(err);
  } finally { hideLoading(); }
}

async function exportChordPro() {
  if (!state.rawText.trim())   { showToast("error", "Nothing to export."); return; }
  if (!state.lastLines.length) { showToast("error", "Transpose first.");   return; }
  showLoading("Preparing ChordPro…");
  try {
    const result = await window.pywebview.api.export_chordpro(..._exportArgs());
    _handleExportResult(result);
  } catch (err) {
    showToast("error", "Export error."); console.error(err);
  } finally { hideLoading(); }
}

async function exportPDF() {
  if (!state.rawText.trim())   { showToast("error", "Nothing to export."); return; }
  if (!state.lastLines.length) { showToast("error", "Transpose first.");   return; }
  showLoading("Generating PDF…");
  try {
    const result = await window.pywebview.api.export_pdf(..._exportArgs(), state.chordColor);
    _handleExportResult(result);
  } catch (err) {
    showToast("error", "Export error."); console.error(err);
  } finally { hideLoading(); }
}

function _handleExportResult(result) {
  if (!result.ok) { showToast("error", result.error || "Export failed."); return; }
  if (result.saved) showToast("success", `Saved: ${result.path.split(/[/\\]/).pop()}`);
  else              showToast("info", "Export cancelled.");
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
  els.chordColorPicker.addEventListener("input", e => {
    applyChordColor(e.target.value);
    els.colorPresets.querySelectorAll(".color-swatch")
      .forEach(s => s.classList.remove("active"));
  });

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
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  document.documentElement.style.setProperty("--chord-bg", `rgba(${r},${g},${b},0.13)`);
}

// ── Font selector ─────────────────────────────────────────────────────────────

function bindFontSelector() {
  els.fontSelect.addEventListener("change", () => {
    els.outputContent.style.fontFamily = els.fontSelect.value;
  });
}

// ── Zoom controls ─────────────────────────────────────────────────────────────

const ZOOM_STEP = 10, ZOOM_MIN = 60, ZOOM_MAX = 220;

function bindZoomControls() {
  els.zoomOut.addEventListener("click",   () => setZoom(state.zoom - ZOOM_STEP));
  els.zoomIn.addEventListener("click",    () => setZoom(state.zoom + ZOOM_STEP));
  els.zoomReset.addEventListener("click", () => setZoom(100));
}

function setZoom(pct) {
  state.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, pct));
  document.documentElement.style.setProperty(
    "--output-size", (14 * state.zoom / 100).toFixed(1) + "px"
  );
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

    state.lastLines = result.lines;
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

  if (els.fontSelect.value) {
    els.outputContent.style.fontFamily = els.fontSelect.value;
  }

  els.editBtn.style.display = "inline-flex";
}

function renderEmpty() {
  els.outputContent.style.display     = "none";
  els.outputPlaceholder.style.display = "flex";
  els.editBtn.style.display           = "none";
  state.lastLines = [];
}

// ── Loading overlay ───────────────────────────────────────────────────────────

function showLoading(msg) {
  els.loadingMsg.textContent       = msg || "Loading…";
  els.loadingOverlay.style.display = "flex";
}

function hideLoading() {
  els.loadingOverlay.style.display = "none";
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
    const inField = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o") {
      e.preventDefault(); openNativeFile(); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "C") {
      e.preventDefault(); copyOutput(); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "E") {
      e.preventDefault(); exportMarkdown(); return;
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === "=" || e.key === "+")) {
      e.preventDefault(); setZoom(state.zoom + ZOOM_STEP); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "-") {
      e.preventDefault(); setZoom(state.zoom - ZOOM_STEP); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "0") {
      e.preventDefault(); setZoom(100); return;
    }

    if (!inField) {
      if (e.key === "ArrowUp"   || e.key === "ArrowRight") { e.preventDefault(); setSemitones(state.semitones + 1); }
      if (e.key === "ArrowDown" || e.key === "ArrowLeft")  { e.preventDefault(); setSemitones(state.semitones - 1); }
    }
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function stripExt(filename) {
  return filename.replace(/\.[^/.]+$/, "");
}
