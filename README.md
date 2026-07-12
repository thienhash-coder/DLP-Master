# DLP Master

DLP Master is a desktop/web downloader interface built on top of `yt-dlp`. It provides a simple Vietnamese UI for downloading videos, playlists, channels, and audio with common presets such as best quality, MP4, and MP3.

The project bundles the `yt_dlp` Python package as the download core and wraps the interface with Electron so the app can be packaged for Windows and updated through GitHub Releases.

## Features

- Download video, playlist, or channel URLs using `yt-dlp`
- Choose best quality, MP4 video, or MP3 audio
- Optional metadata, thumbnail, subtitle, SponsorBlock, and Chrome cookie support
- Admin login with live download logs over WebSocket
- Electron packaging with `electron-builder`
- Auto-update support through GitHub Releases via `electron-updater`

## Project Structure

```text
main.js              Electron main process and auto-update hook
index.html           Downloader UI
fastapi-main.py      FastAPI backend used by the UI
yt_dlp/              Bundled yt-dlp core
downloads/           Default download output directory
package.json         Electron build and release configuration
```

## Requirements

- Node.js and npm
- Python 3.10+
- FFmpeg and FFprobe available on PATH for merging, metadata, thumbnails, and MP3 conversion

## Development

Install Node dependencies:

```bash
npm install
```

Run the FastAPI backend:

```bash
python -m uvicorn fastapi-main:app --host 127.0.0.1 --port 8000 --reload
```

Run the Electron app:

```bash
npm start
```

The default admin account in the current development config is:

```text
Username: admin
Password: password123
```

Change `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` in `fastapi-main.py` before sharing or deploying the app.

## Build

Create a Windows package:

```bash
npm run dist
```

For a quick unpacked build check:

```bash
npm run dist -- --dir
```

Build output is written to `dist/`.

## Releases and Auto Update

Auto-update is configured for:

```text
https://github.com/thienhash-coder/dlp-master
```

To publish a new release:

1. Commit all changes.
2. Increase the app version:

```bash
npm version patch
```

3. Set a GitHub token that can create releases:

```powershell
$env:GH_TOKEN="YOUR_GITHUB_TOKEN"
```

4. Build and publish:

```bash
npm run publish
```

Installed app builds check GitHub Releases on startup. Development runs skip update checks.

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
