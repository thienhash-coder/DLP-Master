from __future__ import annotations

import shutil
from pathlib import Path


SKIP_DIRS = {"backup", "logs", "downloads", "update-cache", "__pycache__"}


def copy_tree_contents(source: str | Path, destination: str | Path, skip_file_names: set[str] | None = None):
    source_path = Path(source)
    destination_path = Path(destination)
    skip_file_names = skip_file_names or set()
    destination_path.mkdir(parents=True, exist_ok=True)

    for item in source_path.iterdir():
        if item.name in SKIP_DIRS:
            continue
        target = destination_path / item.name
        if item.is_dir():
            if target.exists() and not target.is_dir():
                target.unlink()
            copy_tree_contents(item, target, skip_file_names=skip_file_names)
        else:
            if item.name in skip_file_names:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def remove_tree(path: str | Path):
    target = Path(path)
    if target.exists():
        shutil.rmtree(target)

