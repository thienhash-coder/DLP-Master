from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from packaging.version import InvalidVersion, Version


class UpdateCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    minimum_version: str
    download_url: str
    sha256: str
    release_notes: str
    channel: str = "stable"

    @property
    def parsed_version(self) -> Version:
        return Version(self.version)

    @property
    def parsed_minimum_version(self) -> Version:
        return Version(self.minimum_version)


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    is_supported: bool
    manifest: UpdateManifest


class VersionChecker:
    def __init__(self, update_url: str, current_version: str, app_name: str = "DLP Master", channel: str = "stable"):
        self.update_url = (update_url or "").strip()
        self.current_version = (current_version or "").strip().lstrip("vV")
        self.app_name = app_name
        self.channel = (channel or "stable").strip().lower()

    def fetch_manifest(self, timeout: int = 10) -> UpdateManifest:
        if not self.update_url:
            raise UpdateCheckError("UPDATE_URL is empty")

        request = urllib.request.Request(
            self.update_url,
            headers={"User-Agent": f"{self.app_name}/{self.current_version}"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_payload = response.read().decode("utf-8", errors="replace")

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise UpdateCheckError(f"Invalid update JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise UpdateCheckError("Update manifest must be a JSON object")

        version = str(payload.get("version") or "").strip().lstrip("vV")
        minimum_version = str(payload.get("minimum_version") or "0.0.0").strip().lstrip("vV")
        download_url = str(payload.get("download_url") or "").strip()
        sha256 = str(payload.get("sha256") or "").strip()
        release_notes = str(payload.get("release_notes") or payload.get("notes") or "").strip()
        channel = str(payload.get("channel") or "stable").strip().lower()

        if not version:
            raise UpdateCheckError("Update manifest is missing version")
        if not download_url:
            raise UpdateCheckError("Update manifest is missing download_url")
        manifest = UpdateManifest(
            version=version,
            minimum_version=minimum_version,
            download_url=download_url,
            sha256=sha256,
            release_notes=release_notes,
            channel=channel,
        )

        try:
            manifest.parsed_version
            manifest.parsed_minimum_version
        except InvalidVersion as exc:
            raise UpdateCheckError(f"Invalid update version: {exc}") from exc

        if self.channel != "nightly" and manifest.channel not in {self.channel, "stable"}:
            raise UpdateCheckError(f"Manifest channel '{manifest.channel}' does not match '{self.channel}'")

        return manifest

    def check(self, timeout: int = 10) -> UpdateCheckResult:
        try:
            current = Version(self.current_version)
        except InvalidVersion as exc:
            raise UpdateCheckError(f"Invalid current version: {self.current_version}") from exc

        manifest = self.fetch_manifest(timeout=timeout)
        latest = manifest.parsed_version
        minimum = manifest.parsed_minimum_version
        return UpdateCheckResult(
            current_version=str(current),
            latest_version=str(latest),
            update_available=latest > current,
            is_supported=current >= minimum,
            manifest=manifest,
        )
