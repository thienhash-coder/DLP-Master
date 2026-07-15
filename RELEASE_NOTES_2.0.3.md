# DLP Master Qt v2.0.3

## Artifact
- `DLP-Master-Qt-v2.0.3-win64.zip`
- Size: `385.07 MB`
- SHA256: `56325424BBC94C9A033436901644BC307BED4A1D3E55BC65D9C1513EE78EE31D`

## Changes
- Added a professional auto-update foundation with a standalone updater executable.
- Added `update/` modules for version checking, streaming download, SHA256 verification, updater launch, logging, and update dialog UI.
- Added `updater/` modules for backup, safe ZIP extraction, install, rollback, logging, and restart flow.
- Added `Updater.spec` to build `DLP Master Updater.exe`.
- Updated `DLP Master Qt.spec` so the main Qt package bundles `DLP Master Updater.exe` when it has already been built.
- Added update channel support: `stable`, `beta`, and `nightly`.

## Build Order
```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm Updater.spec
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm "DLP Master Qt.spec"
```

## Manifest Format
```json
{
  "version": "2.0.3",
  "minimum_version": "2.0.0",
  "channel": "stable",
  "download_url": "https://github.com/thienhash-coder/dlp-master/releases/download/v2.0.3/DLP-Master-Qt-v2.0.3-win64.zip",
  "sha256": "56325424BBC94C9A033436901644BC307BED4A1D3E55BC65D9C1513EE78EE31D",
  "release_notes": "Release notes shown inside the app."
}
```

## Important
- `download_url` must point directly to the ZIP asset, not the GitHub release page.
- `sha256` is filled with the final ZIP checksum and must match the uploaded asset.
- The main app never overwrites itself; it launches `DLP Master Updater.exe` and exits.
