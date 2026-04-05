#!/usr/bin/env python3
"""
build.py — Cross-platform packaging script for Chord Transposer.

Usage:
    python build.py [--onefile] [--debug]

Outputs:
    dist/ChordTransposer/         (one-dir, recommended)
    dist/ChordTransposer.exe      (Windows, --onefile)
    dist/ChordTransposer.app/     (macOS, --windowed)

Requirements:
    pip install pyinstaller pywebview
"""

import os
import platform
import subprocess
import sys


def main():
    onefile = "--onefile" in sys.argv
    debug   = "--debug"   in sys.argv
    system  = platform.system()   # "Windows" | "Darwin" | "Linux"

    here   = os.path.dirname(os.path.abspath(__file__))
    entry  = os.path.join(here, "main.py")
    ui_dir = os.path.join(here, "ui")

    sep      = ";" if system == "Windows" else ":"
    add_data = [f"--add-data={ui_dir}{sep}ui"]

    # ── Platform flags ───────────────────────────────────────────────────────
    platform_flags = [
        "--windowed",      # No console window on any platform
        "--noconsole",     # Alias for older PyInstaller versions
    ]

    if system == "Darwin":
        platform_flags += [
            "--osx-bundle-identifier=com.chordtransposer.app",
        ]

    # ── Hidden imports for pywebview ─────────────────────────────────────────
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

    cmd.append("--onefile" if onefile else "--onedir")

    if not debug:
        cmd.append("--log-level=WARN")

    cmd += add_data + platform_flags + hidden
    cmd.append(entry)

    print("=" * 60)
    print(f"Building Chord Transposer for {system}")
    print(f"Mode   : {'one-file' if onefile else 'one-dir'}")
    print(f"Console: hidden (windowed mode)")
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
        print(f"   Executable : dist/{name}")
    else:
        print("   Directory  : dist/ChordTransposer/")
    if system == "Darwin":
        print("   App bundle : dist/ChordTransposer.app/")


if __name__ == "__main__":
    main()
