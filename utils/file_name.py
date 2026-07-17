from __future__ import annotations

import re
import unicodedata
from pathlib import Path


class FilenameFormatter:
    """Format metadata titles into stable Windows-safe filenames while keeping Unicode."""

    _WINDOWS_FORBIDDEN = re.compile(r'[<>:"/\\|?*]')
    _TRAILING_HASHTAGS = re.compile(r'(?:\s+#(?:fyp|viral|xuhuong|shorts|tiktok))+\s*$', re.IGNORECASE)
    _UNDERSCORE_RUNS = re.compile(r'_+')
    _SPACE_RUNS = re.compile(r'\s+')
    _EMOJI_PATTERN = re.compile(
        "["
        "\U0001F300-\U0001FAFF"
        "\U00002600-\U000027BF"
        "\U0001F1E6-\U0001F1FF"
        "\u2764\uFE0F"
        "]+",
        flags=re.UNICODE,
    )

    def __init__(self, max_length: int = 120, fallback_title: str = "Untitled"):
        self.max_length = max(1, int(max_length))
        self.fallback_title = fallback_title

    def sanitize_title(self, title: str | None) -> str:
        text = unicodedata.normalize("NFC", str(title or ""))
        text = self._TRAILING_HASHTAGS.sub("", text)
        text = self._EMOJI_PATTERN.sub("", text)
        text = self._WINDOWS_FORBIDDEN.sub(" ", text)
        text = self._UNDERSCORE_RUNS.sub(" ", text)
        text = self._SPACE_RUNS.sub(" ", text).strip()
        text = self._truncate_without_cutting_word(text)
        return text or self.fallback_title

    def build_filename(self, title: str | None, ext: str | None) -> str:
        stem = self.sanitize_title(title)
        normalized_ext = self._normalize_ext(ext)
        return f"{stem}.{normalized_ext}" if normalized_ext else stem

    def make_unique_filename(self, title: str | None, ext: str | None, directory: str | Path) -> str:
        stem = self.sanitize_title(title)
        normalized_ext = self._normalize_ext(ext)
        folder = Path(directory)

        candidate = stem
        index = 1
        while self._path_exists(folder, candidate, normalized_ext):
            candidate = f"{stem} ({index})"
            index += 1

        return f"{candidate}.{normalized_ext}" if normalized_ext else candidate

    def _truncate_without_cutting_word(self, text: str) -> str:
        if len(text) <= self.max_length:
            return text

        clipped = text[: self.max_length].rstrip()
        if not clipped:
            return ""

        split_at = clipped.rfind(" ")
        if split_at > 0:
            clipped = clipped[:split_at].rstrip()

        return clipped

    @staticmethod
    def _normalize_ext(ext: str | None) -> str:
        cleaned = unicodedata.normalize("NFC", str(ext or "")).strip().lstrip(".")
        return cleaned

    @staticmethod
    def _path_exists(folder: Path, stem: str, ext: str) -> bool:
        name = f"{stem}.{ext}" if ext else stem
        return (folder / name).exists()
