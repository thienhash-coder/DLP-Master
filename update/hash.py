from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_sha256(path: str | Path, expected_sha256: str) -> bool:
    expected = (expected_sha256 or "").strip().upper()
    if not expected:
        return False
    return sha256_file(path) == expected

