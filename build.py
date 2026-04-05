#!/usr/bin/env python3
"""
build.py — Cross-platform packaging script for Chord Transposer.

Usage:
    python build.py [--onefile] [--debug]

Outputs:
    dist/ChordTransposer          (Linux / macOS binary)
    dist/ChordTransposer.exe      (Windows)
    dist/ChordTransposer.app/     (macOS .app bundle via --windowed)

Requirements:
    pip install pyinstaller pywebview

The script auto-detects the platform and sets appropriate PyInstaller flags.
"""

import os
import platform
import subprocess
import sys


def main():
    onefile = "--onefile" in sys.argv
    debug   = "--debug"   in sys.argv
    system  = platform.system()   # "Windows", "Darwin", "Linux"

    here   = os.path.dirname(os.path.abspath(__file__))
    entry  = os.path.join(here, "main.py")
    ui_dir = os.path.join(here, "ui")

    # ── Data files (ui/ folder) ──────────────────────────────────────────────
    sep = ";" if system == "Windows" else ":"
    add_data = [
        f"--add-data={ui_dir}{sep}ui",
    ]

    # ── Platform-specific flags ──────────────────────────────────────────────
    platform_flags = []

    if system == "Darwin":
        platform_flags += [
            "--windowed",          # .app bundle, no terminal window
            "--osx-bundle-identifier=com.chordtransposer.app",
            "--icon=",             # add --icon=path/to/icon.icns if you have one
        ]
    elif system == "Windows":
        platform_flags += [
            "--windowed",          # no console window on Windows
            # "--icon=path/to/icon.ico",
        ]
    # Linux: no special flags needed

    # ── PyInstaller hidden imports for pywebview ─────────────────────────────
    hidden = [
        "--hidden-import=webview",
        "--hidden-import=webview.platforms",
    ]

    if system == "Windows":
        hidden += ["--hidden-import=webview.platforms.winforms"]
    elif system == "Darwin":
        hidden += ["--hidden-import=webview.platforms.cocoa"]
    else:
        hidden += ["--hidden-import=webview.platforms.gtk"]

    # ── Assemble command ─────────────────────────────────────────────────────
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ChordTransposer",
        "--distpath=dist",
        "--workpath=build",
        "--specpath=.",
        "--noconfirm",
        "--clean",
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if not debug:
        cmd.append("--log-level=WARN")

    cmd += add_data
    cmd += platform_flags
    cmd += hidden

    # Strip empty --icon= on platforms where no icon is provided
    cmd = [c for c in cmd if c != "--icon="]

    cmd.append(entry)

    print("=" * 60)
    print(f"Building Chord Transposer for {system}")
    print(f"Mode: {'one-file' if onefile else 'one-dir'}")
    print("=" * 60)
    print(" ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=here)
    if result.returncode != 0:
        print("\n❌ Build failed.")
        sys.exit(result.returncode)

    print("\n✅ Build succeeded.")
    if onefile:
        name = "ChordTransposer.exe" if system == "Windows" else "ChordTransposer"
        print(f"   Executable: dist/{name}")
    else:
        print("   Output directory: dist/ChordTransposer/")

    if system == "Darwin" and "--windowed" in platform_flags:
        print("   .app bundle: dist/ChordTransposer.app/")


if __name__ == "__main__":
    main()
