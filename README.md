# DLP Master

DLP Master is a Qt desktop downloader interface built on top of `yt-dlp`. It provides a Vietnamese UI for downloading videos, playlists, channels, and audio with common presets such as MP4, MKV, MP3, and FLAC.

## Features

- Download video, playlist, or channel URLs using `yt-dlp`
- Queue manager with parallel downloads
- MP4, MKV, MP3, and FLAC output presets
- Optional subtitle, thumbnail, and SponsorBlock processing
- Embedded login (Qt WebEngine) for capturing cookies
- Release update check from `version.json`

## Project Structure

```text
yt_dlp_qt_gui.py     Main Qt GUI application
yt_dlp_qt_gui.spec   PyInstaller spec (single executable folder build)
DLP Master Qt.spec   PyInstaller spec including ffmpeg binaries
app_config.py        App name/version/update URL settings
version.json         Release metadata consumed by update checker
yt_dlp/              Bundled yt-dlp core
downloads/           Default download output directory
tools/ffmpeg/bin/    Bundled ffmpeg and ffprobe for packaged app
```

## Requirements

- Python 3.10+
- PyQt6 or PySide6
- Optional: `PyQt6-WebEngine` for embedded login/cookie capture
- FFmpeg and FFprobe (already bundled under `tools/ffmpeg/bin` for packaged build)

## Development

Run the Qt app directly:

```bash
python yt_dlp_qt_gui.py
```

If WebEngine is not installed:

```bash
pip install PyQt6-WebEngine
```

The app reads update settings from:

- `app_config.py` (`CURRENT_VERSION`, `UPDATE_URL`)
- `version.json` (release version and download URL)

## Build

Create a Windows Qt package with bundled ffmpeg:

```bash
python -m PyInstaller --noconfirm "DLP Master Qt.spec"
```

Build output is written to `dist/DLP Master Qt/`.

Create a release zip:

```bash
PowerShell Compress-Archive -Path "dist\DLP Master Qt\*" -DestinationPath "dist\DLP-Master-Qt-vX.Y.Z-win64.zip"
```

## Releases and Auto Update

Qt GUI checks for updates at startup and via manual button in Settings.

Update flow:
1. App reads `UPDATE_URL` from `app_config.py`.
2. App fetches `version.json`.
3. If newer version exists, app prompts user and opens `download_url`.

Note: current updater is prompt-and-open-link, not silent auto-install.

## GitHub Setup

If this local project should point to the new repository:

```bash
git remote set-url origin https://github.com/thienhash-coder/dlp-master.git
git push -u origin master
```

## Notes

- `yt-dlp` support changes often as websites change. Keep the bundled `yt_dlp` core updated when download sites break.
- Do not commit personal cookies, downloaded media, secrets, or generated release files.
- This project includes third-party code from `yt-dlp` and its dependencies. Keep `LICENSE` and `THIRD_PARTY_LICENSES.txt` with distributions.
