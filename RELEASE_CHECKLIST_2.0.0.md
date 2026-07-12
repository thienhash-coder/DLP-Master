# Release Checklist 2.0.0

## 1. Pre-flight
- [ ] Confirm app versions are all `2.0.0`:
  - `yt_dlp_qt_gui.py` (`VERSION`)
  - `app_config.py` (`CURRENT_VERSION`)
  - `version.json` (`version` + `download_url`)
- [ ] Run local sanity test: start `dist/DLP Master Qt/DLP Master Qt.exe`
- [ ] Verify update check in app:
  - Settings page button `Kiểm tra cập nhật` works
  - App can read remote `version.json`

## 2. Build & Artifact
- [x] Build Qt GUI with PyInstaller succeeded
- [x] ZIP artifact created:
  - `dist/DLP-Master-Qt-v2.0.0-win64.zip`
- [ ] Optional: compute checksum (SHA256) and store in release notes

## 3. Git Preparation
- [ ] Review changes: `git status`
- [ ] Commit release changes with clear message, for example:
  - `release: bump version to 2.0.0 and update metadata`
- [ ] Create and push tag:
  - `git tag v2.0.0`
  - `git push origin v2.0.0`

## 4. GitHub Release
- [ ] Create new release `v2.0.0` on GitHub
- [ ] Title: `DLP Master Qt v2.0.0`
- [ ] Upload file `DLP-Master-Qt-v2.0.0-win64.zip`
- [ ] Add release notes:
  - Main features/fixes
  - Breaking changes (if any)
  - Upgrade notes for existing users
- [ ] Publish release

## 5. Post-release Validation
- [ ] Open release page and verify asset download works
- [ ] Verify `version.json` on default branch points to `v2.0.0`
- [ ] On a machine with old version, verify app shows update prompt and opens release URL
- [ ] Smoke test downloaded package on clean Windows environment

## 6. Rollback Plan
- [ ] If severe issue found, mark release as pre-release or draft a hotfix `v2.0.1`
- [ ] Update `version.json` to safe version if auto-update should be paused
