from __future__ import annotations

import zipfile
from pathlib import Path


class UnsafeArchiveError(RuntimeError):
    pass


def extract_zip(package_path: str | Path, destination: str | Path) -> Path:
    package = Path(package_path)
    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    root = destination_path.resolve()

    with zipfile.ZipFile(package, "r") as archive:
        for member in archive.infolist():
            target = (destination_path / member.filename).resolve()
            if root != target and root not in target.parents:
                raise UnsafeArchiveError(f"Unsafe archive member: {member.filename}")
        archive.extractall(destination_path)

    return destination_path

