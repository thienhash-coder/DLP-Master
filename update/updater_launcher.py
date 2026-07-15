from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def main_executable_name() -> str:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).name
    return "DLP Master Qt.exe"


def find_updater_executable(root: str | Path | None = None) -> Path:
    root_path = Path(root) if root else app_root()
    candidates = [
        root_path / "DLP Master Updater.exe",
        root_path / "_internal" / "DLP Master Updater.exe",
        Path(__file__).resolve().parents[1] / "updater" / "main.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("DLP Master Updater.exe was not found")


def launch_updater(package_path: str | Path, app_dir: str | Path | None = None, restart: bool = True) -> subprocess.Popen:
    root = Path(app_dir) if app_dir else app_root()
    updater = find_updater_executable(root)
    args = [
        str(updater),
        "--package",
        str(Path(package_path).resolve()),
        "--app-dir",
        str(root.resolve()),
        "--main-exe",
        main_executable_name(),
    ]
    if restart:
        args.append("--restart")

    if updater.suffix.lower() == ".py":
        args.insert(0, sys.executable)

    return subprocess.Popen(args, cwd=str(root))

