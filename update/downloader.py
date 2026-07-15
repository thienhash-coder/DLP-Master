from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class DownloadCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadProgress:
    downloaded: int
    total: int
    percent: int
    speed_bps: float
    eta_seconds: int | None


class ReleaseDownloader:
    def __init__(self, url: str, target_dir: str | Path, app_name: str = "DLP Master"):
        self.url = url
        self.target_dir = Path(target_dir)
        self.app_name = app_name

    def target_path(self, version: str) -> Path:
        parsed = urllib.parse.urlparse(self.url)
        file_name = Path(urllib.parse.unquote(parsed.path)).name.strip()
        if not file_name:
            file_name = f"DLP-Master-Qt-v{version}-win64.zip"
        return self.target_dir / file_name

    def download(
        self,
        version: str,
        progress_callback=None,
        cancel_callback=None,
        retry_count: int = 2,
        timeout: int = 30,
    ) -> Path:
        self.target_dir.mkdir(parents=True, exist_ok=True)
        target = self.target_path(version)
        partial = target.with_suffix(target.suffix + ".part")

        last_error: Exception | None = None
        for attempt in range(retry_count + 1):
            try:
                return self._download_once(target, partial, progress_callback, cancel_callback, timeout)
            except DownloadCancelled:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= retry_count:
                    break
                time.sleep(1 + attempt)
        raise RuntimeError(f"Download failed: {last_error}") from last_error

    def _download_once(self, target: Path, partial: Path, progress_callback, cancel_callback, timeout: int) -> Path:
        resume_from = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": self.app_name}
        if resume_from:
            headers["Range"] = f"bytes={resume_from}-"

        request = urllib.request.Request(self.url, headers=headers)
        start_time = time.monotonic()
        downloaded = resume_from

        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if resume_from and exc.code == 416:
                partial.replace(target)
                return target
            raise

        with response:
            if resume_from and response.status != 206:
                resume_from = 0
                downloaded = 0

            total_header = response.headers.get("Content-Length")
            total_remaining = int(total_header) if total_header and total_header.isdigit() else 0
            total = total_remaining + resume_from if total_remaining else 0
            mode = "ab" if resume_from else "wb"

            with partial.open(mode) as file:
                while True:
                    if cancel_callback and cancel_callback():
                        raise DownloadCancelled("Download cancelled")

                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    file.write(chunk)
                    downloaded += len(chunk)

                    elapsed = max(time.monotonic() - start_time, 0.001)
                    speed = max((downloaded - resume_from) / elapsed, 0.0)
                    percent = int(downloaded * 100 / total) if total else 0
                    eta = int((total - downloaded) / speed) if total and speed > 0 else None
                    if progress_callback:
                        progress_callback(DownloadProgress(downloaded, total, min(percent, 100), speed, eta))

        partial.replace(target)
        return target

