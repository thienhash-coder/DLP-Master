from __future__ import annotations

from pathlib import Path

from updater.fileops import copy_tree_contents, remove_tree


def restore_backup(backup_dir: str | Path, app_dir: str | Path, skip_file_names: set[str] | None = None):
    app_path = Path(app_dir)
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    copy_tree_contents(backup_path, app_path, skip_file_names=skip_file_names)


def cleanup_backup(backup_dir: str | Path):
    remove_tree(backup_dir)

