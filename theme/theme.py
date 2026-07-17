from __future__ import annotations

import sys
from pathlib import Path

THEME_DIR = Path(__file__).resolve().parent
DEFAULT_THEME = "dark"


THEME_TOKENS = {
    "dark": {
        "BG": "#1e1e1e",
        "CARD": "#252526",
        "SURFACE": "#1f2023",
        "BORDER": "#2d2d30",
        "ACCENT": "#3b82f6",
        "HOVER": "#2d2d30",
        "TEXT": "#e6edf3",
        "MUTED": "#9ca3af",
    },
    "light": {
        "BG": "#f3f4f6",
        "CARD": "#ffffff",
        "SURFACE": "#ffffff",
        "BORDER": "#d1d5db",
        "ACCENT": "#2563eb",
        "HOVER": "#f3f4f6",
        "TEXT": "#1f2937",
        "MUTED": "#4b5563",
    },
}


def _apply_tokens(raw_qss: str, theme_name: str) -> str:
    tokens = THEME_TOKENS.get(theme_name, THEME_TOKENS[DEFAULT_THEME])
    rendered = raw_qss
    for key, value in tokens.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _candidate_theme_dirs() -> list[Path]:
    dirs: list[Path] = [THEME_DIR]

    # PyInstaller onefile/onedir runtime extraction directory.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "theme")

    # Executable directory and common _internal layout.
    exe_dir = Path(sys.executable).resolve().parent
    dirs.append(exe_dir / "theme")
    dirs.append(exe_dir / "_internal" / "theme")

    unique_dirs: list[Path] = []
    seen: set[str] = set()
    for directory in dirs:
        key = str(directory)
        if key in seen:
            continue
        seen.add(key)
        unique_dirs.append(directory)
    return unique_dirs


def _default_stylesheet(theme_name: str) -> str:
    if theme_name == "light":
        return (
            "QWidget { background-color: #f3f4f6; color: #1f2937; "
            "font-family: 'Segoe UI'; font-size: 10pt; }"
        )
    return (
        "QWidget { background-color: #1e1e1e; color: #e6edf3; "
        "font-family: 'Segoe UI'; font-size: 10pt; }"
    )


def load_stylesheet(theme_name: str = DEFAULT_THEME) -> str:
    normalized = str(theme_name or DEFAULT_THEME).strip().lower()
    requested = normalized if normalized in THEME_TOKENS else DEFAULT_THEME

    for theme_dir in _candidate_theme_dirs():
        target = theme_dir / f"{requested}.qss"
        if target.exists():
            return _apply_tokens(target.read_text(encoding="utf-8"), requested)

    # Final fallback to dark file if requested theme is missing.
    for theme_dir in _candidate_theme_dirs():
        target = theme_dir / "dark.qss"
        if target.exists():
            return _apply_tokens(target.read_text(encoding="utf-8"), "dark")

    # Never crash app startup when stylesheet files are missing in packaged builds.
    return _default_stylesheet(requested)


def apply_theme(widget, theme_name: str = DEFAULT_THEME):
    widget.setStyleSheet(load_stylesheet(theme_name))
