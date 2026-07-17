from __future__ import annotations

import os
import re
import json
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

QT_BINDING = ""

try:
    from PyQt6.QtCore import QObject, QLockFile, QThread, QTimer, QUrl, pyqtSignal
    from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QStackedWidget,
        QTextBrowser,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_BINDING = "PyQt6"
except ImportError:
    try:
        from PySide6.QtCore import QObject, QLockFile, QThread, QTimer, QUrl, Signal as pyqtSignal
        from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QProgressBar,
            QPushButton,
            QScrollArea,
            QStackedWidget,
            QTextBrowser,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        QT_BINDING = "PySide6"
    except ImportError:
        print("Can cai PyQt6 hoac PySide6 de chay GUI:")
        print("  pip install PyQt6")
        sys.exit(1)

WEBENGINE_AVAILABLE = True
QWebEngineView = None
QWebEngineProfile = None

try:
    if QT_BINDING == "PyQt6":
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    else:
        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    WEBENGINE_AVAILABLE = False


BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
MAX_CONCURRENT_DOWNLOADS = 2
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
VERSION = "2.0.3"

try:
    from app_config import APP_NAME as CONFIG_APP_NAME, CURRENT_VERSION as CONFIG_CURRENT_VERSION, UPDATE_URL
    try:
        from app_config import UPDATE_CHANNEL as CONFIG_UPDATE_CHANNEL
    except Exception:
        CONFIG_UPDATE_CHANNEL = "stable"
except Exception:
    CONFIG_APP_NAME = "DLP Master"
    CONFIG_CURRENT_VERSION = VERSION
    UPDATE_URL = ""
    CONFIG_UPDATE_CHANNEL = "stable"

from update.downloader import DownloadCancelled, DownloadProgress, ReleaseDownloader
from update.hash import verify_sha256
from update.update_dialog import UpdateDialog
from update.updater_launcher import app_root, launch_updater
from update.version_checker import UpdateCheckError, UpdateCheckResult, VersionChecker
from theme.theme import apply_theme
from widgets.card import CardFrame
from widgets.download_card import DownloadCard
from widgets.header import AppHeader
from widgets.notification import NotificationManager
from widgets.queue_table import QueueTable
from widgets.settings_card import SettingsCard
from widgets.sidebar import AppSidebar
from widgets.statusbar import AppStatusBar
from widgets.update_card import UpdateCard
from utils.file_name import FilenameFormatter

PLATFORM_LOGIN_URLS = {
    "TikTok": "https://www.tiktok.com/login",
    "YouTube": "https://accounts.google.com/signin/v2/identifier?service=youtube",
    "Facebook": "https://www.facebook.com/login",
    "Douyin (抖音)": "https://www.douyin.com/?show_login=1",
    "Kuaishou (快手 - YT Trung Quốc)": "https://www.kuaishou.com/"
}

PLATFORM_AUTH_COOKIE_HINTS = {
    "TikTok": {
        "domains": ("tiktok.com",),
        "auth_cookies": {"sessionid", "sessionid_ss", "sid_tt", "uid_tt", "tt_csrf_token"},
    },
    "YouTube": {
        "domains": ("youtube.com", "google.com"),
        "auth_cookies": {"sid", "hsid", "ssid", "apisid", "sapisid", "__secure-3psid"},
    },
    "Facebook": {
        "domains": ("facebook.com",),
        "auth_cookies": {"c_user", "xs", "fr", "datr"},
    },
    "Douyin (抖音)": {
        "domains": ("douyin.com", "amemv.com"),
        "auth_cookies": {"passport_csrf_token", "sessionid", "sessionid_ss", "uid_tt", "sid_tt", "odin_tt"},
    },
    "Kuaishou (快手 - YT Trung Quốc)": {
        "domains": ("kuaishou.com", "gifshow.com"),
        "auth_cookies": {"kpf", "kpn", "clientid", "did", "didv", "passToken", "userId"},
    },
}


def clean_log_text(message: object) -> str:
    return ANSI_RE.sub("", str(message))


def detect_ffmpeg_bin() -> tuple[str | None, str | None]:
    local_ffmpeg_dir = BASE_DIR / "tools" / "ffmpeg" / "bin"
    local_ffmpeg = local_ffmpeg_dir / "ffmpeg.exe"
    if local_ffmpeg.exists():
        os.environ["PATH"] = f"{local_ffmpeg_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        return str(local_ffmpeg), str(local_ffmpeg_dir)

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path, str(Path(ffmpeg_path).parent)
    return None, None


FFMPEG_PATH, FFMPEG_BIN = detect_ffmpeg_bin()
APP_INSTANCE_LOCK = None


@dataclass
class AppSettings:
    output_format: str = "MP4"
    write_subs: bool = False
    embed_subs_checkbox: bool = False
    embed_thumbnail: bool = False
    sponsorblock: bool = False
    cookie_file: str = ""
    output_dir: str = ""


@dataclass
class DownloadTask:
    task_id: str
    url: str


@dataclass
class CapturedCookie:
    name: str
    value: str
    domain: str
    path: str
    secure: bool
    expires: int
    http_only: bool


@dataclass
class ReleaseInfo:
    version: str
    download_url: str
    notes: str = ""


@dataclass
class QueueRowState:
    task_id: str
    url: str
    title: str
    status: str = "Queued"
    progress: str = "0%"
    speed: str = "-"
    eta: str = "-"
    size: str = "-"
    format_label: str = "-"
    details: str = "-"


def parse_version_tuple(version_text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(version_text))
    return tuple(int(part) for part in parts)


def is_remote_version_newer(remote_version: str, local_version: str) -> bool:
    remote_tuple = parse_version_tuple(remote_version)
    local_tuple = parse_version_tuple(local_version)
    if remote_tuple and local_tuple:
        max_len = max(len(remote_tuple), len(local_tuple))
        remote_norm = remote_tuple + (0,) * (max_len - len(remote_tuple))
        local_norm = local_tuple + (0,) * (max_len - len(local_tuple))
        return remote_norm > local_norm
    return str(remote_version).strip().lower() != str(local_version).strip().lower()


def parse_release_info(raw_payload: str) -> ReleaseInfo | None:
    text = (raw_payload or "").strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        version = str(
            payload.get("version")
            or payload.get("latest_version")
            or payload.get("tag_name")
            or ""
        ).strip()
        version = version.lstrip("vV")
        download_url = str(
            payload.get("download_url")
            or payload.get("url")
            or payload.get("html_url")
            or payload.get("release_url")
            or ""
        ).strip()
        notes = str(payload.get("notes") or payload.get("changelog") or "").strip()

        assets = payload.get("assets")
        if not download_url and isinstance(assets, list):
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                candidate = str(asset.get("browser_download_url") or asset.get("url") or "").strip()
                if candidate:
                    download_url = candidate
                    break

        if version or download_url:
            return ReleaseInfo(version=version, download_url=download_url, notes=notes)

    if text.lower().startswith(("http://", "https://")):
        return ReleaseInfo(version="", download_url=text)

    return ReleaseInfo(version=text.lstrip("vV"), download_url="")


def simplify_release_notes(version: str, notes_text: str) -> str:
    raw_lines = [line.strip(" -*\t") for line in str(notes_text or "").splitlines() if line.strip()]
    picked: list[str] = []
    for line in raw_lines:
        lowered = line.lower()
        if any(token in lowered for token in ("http", "sha", "commit", "merge", "pull request", "issue #")):
            continue
        if len(line) < 4:
            continue
        picked.append(line[:120])
        if len(picked) >= 4:
            break

    if not picked:
        picked = [
            "Improve download stability",
            "Refine platform compatibility",
            "Enhance update experience",
        ]

    safe_version = str(version or "-").strip()
    lines = [f"Version {safe_version}", ""]
    lines.extend([f"✓ {item}" for item in picked])
    return "\n".join(lines)


class DownloadSignals(QObject):
    log = pyqtSignal(str, str)
    metadata = pyqtSignal(str, str, str)
    progress = pyqtSignal(str, int, str, str)
    finished = pyqtSignal(str, bool, str)


class QtYtDlpLogger:
    def __init__(self, signals: DownloadSignals, task_id: str, is_cancelled=None):
        self.signals = signals
        self.task_id = task_id
        self.is_cancelled = is_cancelled

    def _can_emit(self) -> bool:
        if not self.is_cancelled:
            return True
        try:
            return not bool(self.is_cancelled())
        except Exception:
            return True

    def debug(self, message: str, *args, **kwargs):
        if not self._can_emit():
            return
        msg = clean_log_text(message)
        if msg.startswith("[debug]"):
            return
        self.signals.log.emit("info", f"[{self.task_id}] {msg}")

    def info(self, message: str, *args, **kwargs):
        if not self._can_emit():
            return
        self.signals.log.emit("info", f"[{self.task_id}] {clean_log_text(message)}")

    def warning(self, message: str, *args, **kwargs):
        if not self._can_emit():
            return
        self.signals.log.emit("warning", f"[{self.task_id}] {clean_log_text(message)}")

    def error(self, message: str, *args, **kwargs):
        if not self._can_emit():
            return
        self.signals.log.emit("error", f"[{self.task_id}] {clean_log_text(message)}")


class DownloadWorker(QObject):
    def __init__(self, task: DownloadTask, settings: AppSettings):
        super().__init__()
        self.task = task
        self.settings = settings
        self.filename_formatter = FilenameFormatter(max_length=120, fallback_title="Untitled")
        self.signals = DownloadSignals()
        self.stop_event = threading.Event()
        self._cancel_emitted = False

    def stop(self):
        self.stop_event.set()

    def emit_cancelled_once(self):
        if self._cancel_emitted:
            return
        self._cancel_emitted = True
        self.signals.finished.emit(self.task.task_id, False, "Đã dừng bởi người dùng")

    @staticmethod
    def format_bytes(num_bytes: int | float | None) -> str:
        if not num_bytes or num_bytes <= 0:
            return "-"
        value = float(num_bytes)
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1
        return f"{value:.1f} {units[unit_index]}"

    def build_ydl_options(self, allow_subtitles: bool = True) -> dict:
        postprocessors: list[dict] = []
        target_dir = self.settings.output_dir.strip() or str(DOWNLOAD_DIR)
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        opts = {
            "outtmpl": os.path.join(target_dir, "%(title)s.%(ext)s"),
            "logger": QtYtDlpLogger(self.signals, self.task.task_id, is_cancelled=self.stop_event.is_set),
            "progress_hooks": [self.progress_hook],
            "windowsfilenames": False,
            "restrictfilenames": False,
            "match_filter": self._apply_formatted_title,
            "retries": 3,
            "fragment_retries": 3,
            "extractor_retries": 3,
            "sleep_interval_requests": 1,
            "socket_timeout": 15,
            "lazy_playlist": True,
            "noplaylist": False,
            "color": {"stdout": "no_color", "stderr": "no_color"},
        }

        if FFMPEG_BIN:
            opts["ffmpeg_location"] = FFMPEG_BIN

        if self.settings.output_format == "MP4":
            opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"
            opts["merge_output_format"] = "mp4"
        elif self.settings.output_format == "MP4 (Convert)":
            opts["format"] = "bv*+ba/b"
            postprocessors.append(
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }
            )
        elif self.settings.output_format == "MKV":
            opts["format"] = "bv*+ba/b"
            opts["merge_output_format"] = "mkv"
        elif self.settings.output_format == "MP3":
            opts["format"] = "ba/b"
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            )
        elif self.settings.output_format == "FLAC":
            opts["format"] = "ba/b"
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "flac",
                    "preferredquality": "0",
                }
            )
        else:
            opts["format"] = "bv*+ba/b"

        if allow_subtitles:
            if self.settings.write_subs:
                opts["writesubtitles"] = True
                opts["writeautomaticsub"] = True 
                opts["subtitleslangs"] = ["all"] 

            if self.settings.embed_subs_checkbox:
                opts["embedsubtitles"] = True
                if not self.settings.write_subs:
                    opts["writesubtitles"] = True
                    opts["writeautomaticsub"] = True
                    opts["subtitleslangs"] = ["all"]

        if self.settings.embed_thumbnail:
            opts["writethumbnail"] = True
            postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": True})

        if self.settings.sponsorblock:
            postprocessors.append({"key": "SponsorBlock", "categories": ["sponsor"], "when": "after_filter"})
            postprocessors.append(
                {
                    "key": "ModifyChapters",
                    "remove_chapters_patterns": [],
                    "remove_sponsor_segments": ["sponsor"],
                    "remove_ranges": [],
                    "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l",
                    "force_keyframes": False,
                }
            )

        if self.settings.cookie_file and Path(self.settings.cookie_file).exists():
            opts["cookiefile"] = self.settings.cookie_file

        if postprocessors:
            opts["postprocessors"] = postprocessors

        return opts

    def _apply_formatted_title(self, info_dict: dict, *, incomplete=False):
        if not isinstance(info_dict, dict):
            return None

        if info_dict.get("_dlp_title_formatted"):
            return None

        raw_title = info_dict.get("title") or info_dict.get("fulltitle") or info_dict.get("id") or ""
        ext = info_dict.get("ext") or self._expected_extension()
        target_dir = self.settings.output_dir.strip() or str(DOWNLOAD_DIR)

        unique_filename = self.filename_formatter.make_unique_filename(raw_title, ext, target_dir)
        info_dict["title"] = Path(unique_filename).stem
        info_dict["_dlp_title_formatted"] = True
        return None

    def _expected_extension(self) -> str:
        return {
            "MP4": "mp4",
            "MP4 (Convert)": "mp4",
            "MKV": "mkv",
            "MP3": "mp3",
            "FLAC": "flac",
        }.get(self.settings.output_format, "")

    @staticmethod
    def is_subtitle_rate_limit_error(error_text: str) -> bool:
        message = error_text.lower()
        return (
            "unable to download video subtitles" in message
            and ("http error 429" in message or "too many requests" in message)
        )

    @staticmethod
    def is_rate_limit_error(error_text: str) -> bool:
        message = error_text.lower()
        return "http error 429" in message or "too many requests" in message

    def progress_hook(self, status: dict):
        if self.stop_event.is_set():
            raise DownloadError("Đã dừng bởi người dùng")

        info_dict = status.get("info_dict") or {}
        hook_title = info_dict.get("title")
        hook_size = info_dict.get("filesize") or info_dict.get("filesize_approx")
        if hook_title:
            self.signals.metadata.emit(self.task.task_id, str(hook_title), self.format_bytes(hook_size))

        state = status.get("status")
        if state == "downloading":
            downloaded_bytes = status.get("downloaded_bytes")
            total_bytes = status.get("total_bytes") or status.get("total_bytes_estimate")

            percent_text = str(status.get("_percent_str", "0%")).strip().replace("%", "")
            speed = str(status.get("_speed_str", "-")).strip().replace("~", "")
            eta = str(status.get("_eta_str", "-")).strip()

            try:
                percent = max(0, min(100, int(float(percent_text))))
            except ValueError:
                percent = 0

            if downloaded_bytes and total_bytes and total_bytes > 0:
                percent = max(0, min(100, int((float(downloaded_bytes) / float(total_bytes)) * 100)))

            size_progress = f"{self.format_bytes(downloaded_bytes)} / {self.format_bytes(total_bytes)}"
            details = f"{size_progress} | {speed} | ETA {eta}"
            self.signals.progress.emit(self.task.task_id, percent, size_progress, details)
        elif state == "finished":
            total_bytes = status.get("total_bytes") or status.get("downloaded_bytes")
            done_size = self.format_bytes(total_bytes)
            self.signals.progress.emit(self.task.task_id, 100, done_size, f"{done_size} | Đang xử lý hậu kỳ / Chuyển định dạng...")

    def run(self):
        retry_delays = [8, 20, 45]
        try:
            self.signals.log.emit("warning", f"[{self.task.task_id}] Bắt đầu tải: {self.task.url}")
            self.signals.log.emit("info", f"[{self.task.task_id}] Chế độ playlist: vừa quét vừa tải (lazy)")
            self.signals.metadata.emit(self.task.task_id, self.task.url, "-")
            for attempt in range(len(retry_delays) + 1):
                if self.stop_event.is_set():
                    self.emit_cancelled_once()
                    return
                try:
                    with YoutubeDL(self.build_ydl_options(allow_subtitles=True)) as ydl:
                        ydl.download([self.task.url])
                    break
                except DownloadError as err:
                    err_text = clean_log_text(err)

                    if self.settings.embed_subs_checkbox and self.is_subtitle_rate_limit_error(err_text):
                        self.signals.log.emit(
                            "warning",
                            f"[{self.task.task_id}] Phụ đề bị giới hạn 429. Tự động tải lại không kèm phụ đề...",
                        )
                        try:
                            with YoutubeDL(self.build_ydl_options(allow_subtitles=False)) as fallback_ydl:
                                fallback_ydl.download([self.task.url])
                            self.signals.finished.emit(self.task.task_id, True, "Hoàn tất (bỏ qua phụ đề do 429)")
                            return
                        except Exception as fallback_err:
                            err_text = clean_log_text(fallback_err)

                    if self.is_rate_limit_error(err_text) and attempt < len(retry_delays):
                        delay = retry_delays[attempt]
                        self.signals.log.emit(
                            "warning",
                            f"[{self.task.task_id}] Gặp giới hạn 429. Thử lại sau {delay}s ({attempt + 1}/{len(retry_delays)}).",
                        )
                        for _ in range(delay):
                            if self.stop_event.is_set():
                                self.emit_cancelled_once()
                                return
                            time.sleep(1)
                        continue

                    self.signals.log.emit("error", f"[{self.task.task_id}] {err_text}")
                    self.signals.finished.emit(self.task.task_id, False, str(err))
                    return

                except Exception as err:
                    err_text = clean_log_text(err)
                    if self.is_rate_limit_error(err_text) and attempt < len(retry_delays):
                        delay = retry_delays[attempt]
                        self.signals.log.emit(
                            "warning",
                            f"[{self.task.task_id}] Gặp giới hạn 429. Thử lại sau {delay}s ({attempt + 1}/{len(retry_delays)}).",
                        )
                        for _ in range(delay):
                            if self.stop_event.is_set():
                                self.emit_cancelled_once()
                                return
                            time.sleep(1)
                        continue
                    raise

            self.signals.finished.emit(self.task.task_id, True, "Hoàn tất")
        except Exception as err:
            if self.stop_event.is_set():
                self.emit_cancelled_once()
                return
            self.signals.log.emit("error", f"[{self.task.task_id}] {clean_log_text(err)}")
            self.signals.log.emit("error", traceback.format_exc())
            self.signals.finished.emit(self.task.task_id, False, str(err))


class QueueItemWidget(QFrame):
    def __init__(self, task: DownloadTask):
        super().__init__()
        self.task = task
        self.setObjectName("QueueItem")
        self.completed = False
        self.last_size = "-"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.title = QLabel(self.elide_text(task.url))
        self.title.setObjectName("QueueTitle")
        self.title.setToolTip(task.url)
        self.status = QLabel("Đang chờ")
        self.status.setObjectName("QueueStatus")

        header.addWidget(self.title, 1)
        header.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(True)

        self.meta = QLabel("-")
        self.meta.setObjectName("QueueMeta")

        layout.addLayout(header)
        layout.addWidget(self.progress)
        layout.addWidget(self.meta)

    @staticmethod
    def elide_text(text: str, max_len: int = 62) -> str:
        clean = text.strip()
        if len(clean) <= max_len:
            return clean
        return clean[: max_len - 3].rstrip() + "..."

    def set_video_title(self, title: str):
        display = self.elide_text(title)
        self.title.setText(display)
        self.title.setToolTip(title)

    def update_download_state(self, percent: int, size_text: str, details: str):
        self.progress.setValue(percent)
        if size_text and size_text != "-":
            self.last_size = size_text
        self.meta.setText(details)
        if percent >= 100:
            self.status.setText(f"{self.last_size} | Hoàn tất")
        else:
            self.status.setText(f"{self.last_size} | Đang tải")

    def mark_queued(self):
        self.completed = False
        self.status.setText("Đang chờ")
        self.status.setProperty("state", "queued")
        self.style().unpolish(self.status)
        self.style().polish(self.status)

    def mark_running(self):
        self.completed = False
        self.status.setText("Đang tải")
        self.status.setProperty("state", "running")
        self.style().unpolish(self.status)
        self.style().polish(self.status)

    def mark_done(self):
        self.completed = True
        self.status.setText(f"{self.last_size} | Hoàn tất")
        self.status.setProperty("state", "done")
        self.progress.setValue(100)
        self.style().unpolish(self.status)
        self.style().polish(self.status)

    def mark_failed(self):
        self.completed = False
        self.status.setText("Thất bại")
        self.status.setProperty("state", "failed")
        self.style().unpolish(self.status)
        self.style().polish(self.status)

    def mark_cancelled(self):
        self.completed = False
        self.status.setText("Đã dừng")
        self.status.setProperty("state", "cancelled")
        self.style().unpolish(self.status)
        self.style().polish(self.status)

class EmbeddedLoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.selected_platform = "TikTok"
        self.cookie_file_path = ""
        self.cookies: dict[tuple[str, str, str], CapturedCookie] = {}
        self.auto_close_armed = False
        self.opened_at = time.monotonic()
        self.current_url = ""
        self.auth_verified = False

        self.setWindowTitle("Đăng nhập tài khoản")
        self.setModal(True)
        self.resize(980, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.info_label = QLabel("Đang mở trang đăng nhập. Sau khi đăng nhập xong, đóng cửa sổ để lưu cookie tự động.")
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("Hint")

        platform_row = QHBoxLayout()
        platform_label = QLabel("Nền tảng:")
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(list(PLATFORM_LOGIN_URLS.keys()))
        self.platform_combo.setCurrentText(self.selected_platform)
        self.platform_combo.currentTextChanged.connect(self.load_selected_platform)
        self.open_button = QPushButton("Mở trang đăng nhập")
        self.open_button.clicked.connect(self.load_selected_platform)

        platform_row.addWidget(platform_label)
        platform_row.addWidget(self.platform_combo, 1)
        platform_row.addWidget(self.open_button)

        self.view = QWebEngineView()
        self.view.urlChanged.connect(self.on_url_changed)
        self.load_selected_platform(self.selected_platform)

        self.confirm_button = QPushButton("Tôi đã đăng nhập xong - Lưu cookie")
        self.confirm_button.clicked.connect(self.confirm_login_and_close)

        close_button = QPushButton("Đóng cửa sổ đăng nhập")
        close_button.clicked.connect(self.close)

        layout.addWidget(self.info_label)
        layout.addLayout(platform_row)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.confirm_button)
        layout.addWidget(close_button)

        self.cookie_store = QWebEngineProfile.defaultProfile().cookieStore()
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)
        self.cookie_store.cookieRemoved.connect(self.on_cookie_removed)
        self.cookie_store.loadAllCookies()

    def on_url_changed(self, url: QUrl):
        try:
            self.current_url = url.toString()
        except Exception:
            self.current_url = ""

    def load_selected_platform(self, platform_name: str | None = None):
        if platform_name:
            self.selected_platform = platform_name
        else:
            self.selected_platform = self.platform_combo.currentText()
        target_url = PLATFORM_LOGIN_URLS.get(self.selected_platform, PLATFORM_LOGIN_URLS["TikTok"])
        self.opened_at = time.monotonic()
        self.auto_close_armed = False
        self.current_url = target_url
        self.view.load(QUrl(target_url))
        self.info_label.setText(
            "Đang đăng nhập {platform}. Sau khi xong, đóng cửa sổ để lưu cookie tự động.".format(platform=self.selected_platform)
        )
        try:
            self.cookie_store.loadAllCookies()
        except Exception:
            pass

    def on_cookie_added(self, cookie):
        record = self.to_record(cookie)
        if not record:
            return
        key = (record.domain, record.path, record.name)
        self.cookies[key] = record
        self.info_label.setText("Đã ghi nhận {count} cookie. Có thể đóng cửa sổ khi đăng nhập xong.".format(count=len(self.cookies)))
        self.maybe_auto_close_on_login(record)

    def on_cookie_removed(self, cookie):
        record = self.to_record(cookie)
        if not record:
            return
        key = (record.domain, record.path, record.name)
        if key in self.cookies:
            del self.cookies[key]
        self.info_label.setText("Đã ghi nhận {count} cookie. Có thể đóng cửa sổ khi đăng nhập xong.".format(count=len(self.cookies)))

    def to_record(self, cookie) -> CapturedCookie | None:
        try:
            name = bytes(cookie.name()).decode("utf-8", errors="ignore")
            value = bytes(cookie.value()).decode("utf-8", errors="ignore")
            domain = cookie.domain() or ""
            path = cookie.path() or "/"
            secure = bool(cookie.isSecure())
            http_only = bool(cookie.isHttpOnly())
            expires = 0
            expiration = cookie.expirationDate()
            if expiration.isValid():
                expires = int(expiration.toSecsSinceEpoch())
            if not name or not domain:
                return None
            return CapturedCookie(
                name=name,
                value=value,
                domain=domain,
                path=path,
                secure=secure,
                expires=expires,
                http_only=http_only,
            )
        except Exception:
            return None

    def maybe_auto_close_on_login(self, latest: CapturedCookie):
        if self.auto_close_armed:
            return

        config = PLATFORM_AUTH_COOKIE_HINTS.get(self.selected_platform)
        if not config:
            return

        latest_domain = latest.domain.lstrip(".").lower()
        latest_cookie = latest.name.lower()
        allowed_domains = tuple(domain.lower() for domain in config["domains"])
        auth_cookies = {cookie.lower() for cookie in config["auth_cookies"]}

        domain_match = any(latest_domain.endswith(domain) for domain in allowed_domains)
        auth_cookie_match = latest_cookie in auth_cookies
        if not (domain_match and auth_cookie_match):
            return

        platform_cookie_count = 0
        for saved in self.cookies.values():
            saved_domain = saved.domain.lstrip(".").lower()
            if any(saved_domain.endswith(domain) for domain in allowed_domains):
                platform_cookie_count += 1

        if platform_cookie_count < 3:
            return

        if time.monotonic() - self.opened_at < 4.0:
            return

        current = (self.current_url or "").lower()
        if any(token in current for token in ("/login", "signin", "log-in", "accounts.google.com/signin")):
            return

        self.auto_close_armed = True
        self.auth_verified = True
        self.info_label.setText(
            "Đăng nhập {platform} thành công. Cửa sổ sẽ tự động đóng...".format(platform=self.selected_platform)
        )
        QTimer.singleShot(700, self.close)

    def get_platform_cookie_stats(self) -> tuple[int, int]:
        config = PLATFORM_AUTH_COOKIE_HINTS.get(self.selected_platform)
        if not config:
            return 0, 0

        allowed_domains = tuple(domain.lower() for domain in config["domains"])
        auth_cookies = {cookie.lower() for cookie in config["auth_cookies"]}
        platform_count = 0
        auth_count = 0

        for saved in self.cookies.values():
            saved_domain = saved.domain.lstrip(".").lower()
            if not any(saved_domain.endswith(domain) for domain in allowed_domains):
                continue
            platform_count += 1
            if saved.name.lower() in auth_cookies and saved.value:
                auth_count += 1

        return platform_count, auth_count

    def confirm_login_and_close(self):
        platform_count, auth_count = self.get_platform_cookie_stats()
        if auth_count == 0:
            self.info_label.setText(
                "Chưa phát hiện cookie đăng nhập hợp lệ cho {platform}. Đã ghi nhận {total} cookie tổng, {platform_count} cookie nền tảng, {auth_count} cookie đăng nhập.".format(
                    platform=self.selected_platform,
                    total=len(self.cookies),
                    platform_count=platform_count,
                    auth_count=auth_count,
                )
            )
            return

        self.auth_verified = True
        self.info_label.setText(
            "Xác nhận đăng nhập {platform} thành công ({auth_count} cookie đăng nhập). Đang lưu cookie...".format(platform=self.selected_platform, auth_count=auth_count)
        )
        self.close()

    def export_cookie_file(self) -> str:
        if not self.cookies:
            return ""

        config = PLATFORM_AUTH_COOKIE_HINTS.get(self.selected_platform)
        if not config:
            return ""

        allowed_domains = tuple(domain.lower() for domain in config["domains"])
        filtered = [
            record
            for record in self.cookies.values()
            if any(record.domain.lstrip(".").lower().endswith(domain) for domain in allowed_domains)
        ]
        if not filtered:
            return ""

        target = Path(tempfile.gettempdir()) / f"yt_dlp_web_cookie_{uuid.uuid4().hex}.txt"
        lines = [
            "# Netscape HTTP Cookie File\n",
            "# Tệp này được tạo bởi đăng nhập Qt WebEngine nhúng\n",
            "\n",
        ]

        for record in sorted(filtered, key=lambda item: (item.domain, item.path, item.name)):
            include_subdomain = "TRUE" if record.domain.startswith(".") else "FALSE"
            secure_flag = "TRUE" if record.secure else "FALSE"
            domain_field = record.domain
            if record.http_only and not domain_field.startswith("#HttpOnly_"):
                domain_field = f"#HttpOnly_{domain_field}"

            line = (
                f"{domain_field}\t{include_subdomain}\t{record.path}\t{secure_flag}\t"
                f"{record.expires}\t{record.name}\t{record.value}\n"
            )
            lines.append(line)

        target.write_text("".join(lines), encoding="utf-8")
        return str(target)

    def closeEvent(self, event):
        try:
            self.cookie_file_path = self.export_cookie_file()
        finally:
            try:
                self.cookie_store.cookieAdded.disconnect(self.on_cookie_added)
            except Exception:
                pass
            try:
                self.cookie_store.cookieRemoved.disconnect(self.on_cookie_removed)
            except Exception:
                pass
        super().closeEvent(event)

class SettingsDialog(QDialog):
    def __init__(self, current: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt")
        self.setModal(True)
        self.setMinimumWidth(620)

        self.cookie_file_path = current.cookie_file
        self.output_dir = current.output_dir

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        format_label = QLabel("Định dạng")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MP4 (Convert)", "MKV", "MP3", "FLAC"])
        self.format_combo.setCurrentText(current.output_format)

        self.write_subs = QCheckBox("Phụ đề")
        self.write_subs.setChecked(current.write_subs)

        self.embed_subs_checkbox = QCheckBox("Nhúng phụ đề")
        self.embed_subs_checkbox.setChecked(current.embed_subs_checkbox)

        self.embed_thumb = QCheckBox("Ảnh đại diện")
        self.embed_thumb.setChecked(current.embed_thumbnail)

        self.sponsorblock = QCheckBox("Loại bỏ quảng cáo SponsorBlock")
        self.sponsorblock.setChecked(current.sponsorblock)

        self.login_button = QPushButton("Đăng nhập tài khoản để tải video giới hạn")
        self.login_button.setObjectName("LoginButton")
        self.login_button.clicked.connect(self.open_login_dialog)

        self.cookie_status = QLabel()
        self.cookie_status.setWordWrap(True)
        self.cookie_status.setObjectName("Hint")
        self.update_cookie_status()

        webengine_hint = QLabel(
            "Sau khi đăng nhập xong trong cửa sổ trình duyệt nhúng, đóng cửa sổ để lưu cookie vào tệp tạm tự động."
        )
        webengine_hint.setWordWrap(True)
        webengine_hint.setObjectName("Hint")

        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.accept)
        actions.rejected.connect(self.reject)

        layout.addWidget(format_label)
        layout.addWidget(self.format_combo)
        layout.addWidget(self.write_subs)
        layout.addWidget(self.embed_subs_checkbox)
        layout.addWidget(self.embed_thumb)
        layout.addWidget(self.sponsorblock)
        layout.addSpacing(4)
        layout.addWidget(self.login_button)
        layout.addWidget(self.cookie_status)
        layout.addWidget(webengine_hint)
        layout.addSpacing(8)
        layout.addWidget(actions)

        if not WEBENGINE_AVAILABLE:
            self.cookie_status.setText("[đăng nhập] Qt WebEngine chưa sẵn sàng. Cài đặt thêm: pip install PyQt6-WebEngine")

    def update_cookie_status(self):
        if self.cookie_file_path and Path(self.cookie_file_path).exists():
            self.cookie_status.setText("Cookie đang sử dụng: {path}".format(path=self.cookie_file_path))
        else:
            self.cookie_status.setText("Chế độ cookie: Công khai/Ẩn danh (chưa đăng nhập)")

    def open_login_dialog(self):
        if not WEBENGINE_AVAILABLE:
            self.cookie_status.setText("[đăng nhập] Qt WebEngine chưa sẵn sàng. Cài đặt thêm: pip install PyQt6-WebEngine")
            return

        old_cookie = self.cookie_file_path

        dialog = EmbeddedLoginDialog(self)
        dialog.setStyleSheet(self.styleSheet())
        dialog.exec()

        new_cookie_file = dialog.cookie_file_path
        if new_cookie_file and Path(new_cookie_file).exists():
            self.cookie_file_path = new_cookie_file
            if old_cookie and Path(old_cookie).exists() and old_cookie != new_cookie_file:
                try:
                    Path(old_cookie).unlink()
                except OSError:
                    pass
            self.update_cookie_status()
        elif not new_cookie_file:
            self.cookie_status.setText("Chưa thu được cookie nào. Hãy đăng nhập rồi đóng cửa sổ trình duyệt.")

    def get_settings(self) -> AppSettings:
        return AppSettings(
            output_format=self.format_combo.currentText(),
            write_subs=self.write_subs.isChecked(),
            embed_subs_checkbox=self.embed_subs_checkbox.isChecked(),
            embed_thumbnail=self.embed_thumb.isChecked(),
            sponsorblock=self.sponsorblock.isChecked(),
            cookie_file=self.cookie_file_path,
            output_dir=self.output_dir,
        )


class UpdateThread(QThread):
    update_finished = pyqtSignal(bool, str)

    def __init__(self, messages: dict[str, str] | None = None):
        super().__init__()
        self.messages = messages or {}

    def run(self):
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or result.stderr or "").strip()
            if result.returncode == 0:
                message = output or self.messages.get("success", "yt-dlp đã được cập nhật thành công.")
                self.update_finished.emit(True, message)
            else:
                template = self.messages.get("pip_error", "pip kết thúc với mã lỗi {code}.")
                message = output or template.format(code=result.returncode)
                self.update_finished.emit(False, message)
        except Exception as exc:
            self.update_finished.emit(
                False,
                self.messages.get("exception", "Lỗi khi cập nhật yt-dlp: {error}").format(error=exc),
            )


class UpdateCheckThread(QThread):
    update_checked = pyqtSignal(bool, object, str)

    def __init__(self, update_url: str, current_version: str, app_name: str, channel: str):
        super().__init__()
        self.update_url = update_url
        self.current_version = current_version
        self.app_name = app_name
        self.channel = channel

    def run(self):
        try:
            checker = VersionChecker(self.update_url, self.current_version, self.app_name, self.channel)
            result = checker.check()
            self.update_checked.emit(True, result, "")
        except Exception as exc:
            self.update_checked.emit(False, None, clean_log_text(exc))


class UpdateDownloadThread(QThread):
    download_progress = pyqtSignal(int, str)
    download_finished = pyqtSignal(bool, str, str)

    def __init__(self, manifest, target_dir: str, app_name: str, messages: dict[str, str] | None = None):
        super().__init__()
        self.manifest = manifest
        self.target_dir = target_dir
        self.app_name = app_name
        self._cancelled = False
        self.messages = messages or {}

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            downloader = ReleaseDownloader(self.manifest.download_url, self.target_dir, self.app_name)
            package_path = downloader.download(
                self.manifest.version,
                progress_callback=self._emit_progress,
                cancel_callback=lambda: self._cancelled,
            )
            if self._cancelled:
                self.download_finished.emit(False, "", self.messages.get("cancelled", "Đã hủy tải cập nhật"))
                return
            if not verify_sha256(package_path, self.manifest.sha256):
                self.download_finished.emit(False, "", self.messages.get("sha_failed", "Xác minh SHA256 thất bại"))
                return
            self.download_finished.emit(True, str(package_path), self.messages.get("verified", "Đã xác minh tải cập nhật"))
        except DownloadCancelled as exc:
            self.download_finished.emit(False, "", self.messages.get("cancelled", str(exc) or "Đã hủy tải cập nhật"))
        except Exception as exc:
            self.download_finished.emit(False, "", clean_log_text(exc))

    def _emit_progress(self, progress: DownloadProgress):
        speed = self._format_bytes(progress.speed_bps) + "/s"
        eta = self._format_eta(progress.eta_seconds)
        total = self._format_bytes(progress.total) if progress.total else "-"
        downloaded = self._format_bytes(progress.downloaded)
        self.download_progress.emit(progress.percent, f"{downloaded}/{total} | {speed} | ETA {eta}")

    @staticmethod
    def _format_bytes(value: int | float) -> str:
        units = ["B", "KB", "MB", "GB"]
        size = float(value or 0)
        index = 0
        while size >= 1024 and index < len(units) - 1:
            size /= 1024
            index += 1
        return f"{size:.1f} {units[index]}"

    @staticmethod
    def _format_eta(seconds: int | None) -> str:
        if seconds is None:
            return "-"
        minutes, secs = divmod(max(0, int(seconds)), 60)
        return f"{minutes:02d}:{secs:02d}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        DOWNLOAD_DIR.mkdir(exist_ok=True)

        self.is_frozen_build = bool(getattr(sys, "frozen", False))

        self.current_version = (str(CONFIG_CURRENT_VERSION).strip() or VERSION).lstrip("vV")
        self.update_url = str(UPDATE_URL).strip()
        self.update_channel = str(CONFIG_UPDATE_CHANNEL or "stable").strip().lower()
        self.latest_release_url = ""

        self.settings = AppSettings(output_dir=self.get_default_download_dir())
        self.pending_queue: deque[DownloadTask] = deque()
        self.active_threads: dict[str, tuple[QThread, DownloadWorker]] = {}
        self.queue_rows: dict[str, QueueRowState] = {}
        self.force_stop_timers: dict[str, QTimer] = {}
        self.sidebar_buttons: list[QPushButton] = []
        self.update_thread: UpdateThread | None = None
        self.update_check_thread: UpdateCheckThread | None = None
        self.update_download_thread: UpdateDownloadThread | None = None
        self.update_dialog: UpdateDialog | None = None
        self.pending_update_result: UpdateCheckResult | None = None
        self.downloaded_update_package = ""
        self.skipped_update_version = ""
        self.update_prompted_version = ""
        self.notifications: NotificationManager | None = None
        self.runtime_status_timer: QTimer | None = None
        self.network_state_text = "Unknown"
        self.connection_chip_text = "Sẵn sàng"
        self.connection_chip_state = "ok"

        self.setWindowTitle("DLP Master")
        self.resize(1280, 780)
        self.setMinimumSize(1040, 680)
        self._build_ui()
        self._apply_theme()
        self._refresh_runtime_status()
        self._start_runtime_status_timer()

        self.append_log("success", "Bảng điều khiển đã sẵn sàng.")
        if FFMPEG_PATH:
            self.append_log("success", "Đã tìm thấy FFmpeg: {path}".format(path=FFMPEG_PATH))
        else:
            self.append_log("warning", "Không tìm thấy FFmpeg. Các chế độ chuyển đổi video/âm thanh có thể thất bại.")

        if WEBENGINE_AVAILABLE:
            self.append_log("info", "Qt WebEngine đã sẵn sàng.")
        else:
            self.append_log("warning", "Qt WebEngine chưa sẵn sàng. Cài PyQt6-WebEngine để dùng đăng nhập nhúng.")
        self.append_log("info", "Phiên bản ứng dụng: v{version}".format(version=self.current_version))
        self.append_log("info", "Thư mục lưu mặc định: {path}".format(path=self.settings.output_dir))
        self.update_cookie_status()
        QTimer.singleShot(1500, self.check_for_updates_silent)
        if self.is_frozen_build:
            self.append_log("info", "Bỏ qua cập nhật lõi vì đang chạy bản đóng gói.")
        else:
            self.check_core_update()

    def get_default_download_dir(self) -> str:
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.isdir(default_dir):
            return default_dir
        return str(DOWNLOAD_DIR)

    def check_core_update(self):
        if self.is_frozen_build:
            return
        if self.update_thread and self.update_thread.isRunning():
            return
        self.append_log("info", "Đang kiểm tra và cập nhật lõi yt-dlp trong nền...")
        self.update_thread = UpdateThread(
            {
                "success": "yt-dlp đã được cập nhật thành công.",
                "pip_error": "pip kết thúc với mã lỗi {code}.",
                "exception": "Lỗi khi cập nhật yt-dlp: {error}",
            }
        )
        self.update_thread.update_finished.connect(self.on_update_completed)
        self.update_thread.finished.connect(self._clear_update_thread)
        self.update_thread.finished.connect(self.update_thread.deleteLater)
        self.update_thread.start()

    def on_update_completed(self, success, message):
        level = "success" if success else "warning"
        prefix = "Cập nhật lõi yt-dlp hoàn tất" if success else "Cập nhật lõi yt-dlp thất bại"
        if hasattr(self, "append_log"):
            self.append_log(level, f"{prefix}: {message}")
        else:
            print(f"{prefix}: {message}")

    def _clear_update_thread(self):
        self.update_thread = None

    def _build_ui(self):
        root = QWidget()
        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        self.sidebar = AppSidebar(CONFIG_APP_NAME, self.current_version)
        self.sidebar.page_requested.connect(self.switch_page)
        self.sidebar.login_requested.connect(self.open_login_dialog)
        self.sidebar_buttons = self.sidebar.buttons

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")
        self.stack.addWidget(self._build_download_page())
        self.stack.addWidget(self._build_settings_page())
        self.stack.addWidget(self._build_logs_page())
        self.stack.addWidget(self._build_help_page())

        content_column = QVBoxLayout()
        content_column.setContentsMargins(0, 0, 0, 0)
        content_column.setSpacing(10)

        self.top_header = AppHeader(CONFIG_APP_NAME, self.current_version)
        self.bottom_status = AppStatusBar()
        content_column.addWidget(self.top_header)
        content_column.addWidget(self.stack, 1)
        content_column.addWidget(self.bottom_status)

        main_layout.addWidget(self.sidebar)
        main_layout.addLayout(content_column, 1)

        self.setCentralWidget(root)
        self.notifications = NotificationManager(self)
        self.switch_page(0)

    def _build_content_card(self, title_text: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        card = CardFrame(title_text)
        card_layout = card.body_layout()

        page_layout.addWidget(card)
        return page, card_layout

    def _build_download_page(self) -> QWidget:
        page, layout = self._build_content_card("Tải xuống")

        self.download_card = DownloadCard()
        self.url_input = self.download_card.url_input
        self.download_button = self.download_card.start_button
        self.output_path_input = self.download_card.output_input
        self.browse_output_button = self.download_card.browse_button

        self.url_input.returnPressed.connect(self.enqueue_from_input)
        self.download_button.clicked.connect(self.enqueue_from_input)
        self.browse_output_button.clicked.connect(self.choose_download_directory)

        self.queue_table = QueueTable()
        self.queue_table.pause_requested.connect(self.pause_selected_task)
        self.queue_table.resume_requested.connect(self.resume_selected_task)
        self.queue_table.retry_requested.connect(self.retry_selected_task)
        self.queue_table.delete_requested.connect(self.delete_selected_task)

        self.download_card.pause_button.clicked.connect(lambda: self.pause_selected_task(self.queue_table.selected_task_id()))
        self.download_card.resume_button.clicked.connect(lambda: self.resume_selected_task(self.queue_table.selected_task_id()))
        self.download_card.retry_button.clicked.connect(lambda: self.retry_selected_task(self.queue_table.selected_task_id()))
        self.download_card.delete_button.clicked.connect(lambda: self.delete_selected_task(self.queue_table.selected_task_id()))

        queue_host_layout = QVBoxLayout(self.download_card.queue_placeholder)
        queue_host_layout.setContentsMargins(0, 0, 0, 0)
        queue_host_layout.setSpacing(8)

        queue_action_row = QHBoxLayout()
        self.stop_all_button = QPushButton("Dừng tất cả")
        self.stop_all_button.setObjectName("QueueDangerButton")
        self.stop_all_button.setToolTip("Dừng tất cả tác vụ đang chờ và đang tải.")
        self.stop_all_button.clicked.connect(self.stop_all_tasks)

        self.clear_completed_button = QPushButton("Xóa đã hoàn thành")
        self.clear_completed_button.setToolTip("Xóa các tác vụ đã hoàn thành, thất bại hoặc đã dừng.")
        self.clear_completed_button.clicked.connect(self.clear_completed_items)

        queue_action_row.addStretch(1)
        queue_action_row.addWidget(self.clear_completed_button)
        queue_action_row.addWidget(self.stop_all_button)

        queue_host_layout.addLayout(queue_action_row)
        queue_host_layout.addWidget(self.queue_table, 1)

        self.output_path_input.setText(self.settings.output_dir)
        layout.addWidget(self.download_card, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._build_content_card("Cài đặt")

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        download_card = SettingsCard("Thiết lập tải xuống")
        download_layout = download_card.content_layout()
        format_row = QHBoxLayout()
        format_label = QLabel("Định dạng")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MP4 (Convert)", "MKV", "MP3", "FLAC"])
        self.format_combo.setCurrentText(self.settings.output_format)
        format_row.addWidget(format_label)
        format_row.addWidget(self.format_combo, 1)

        self.write_subs_checkbox = QCheckBox("Phụ đề")
        self.write_subs_checkbox.setChecked(self.settings.write_subs)
        self.embed_subs_checkbox = QCheckBox("Nhúng phụ đề")
        self.embed_subs_checkbox.setChecked(self.settings.embed_subs_checkbox)
        self.embed_thumb_checkbox = QCheckBox("Ảnh đại diện")
        self.embed_thumb_checkbox.setChecked(self.settings.embed_thumbnail)
        self.sponsorblock_checkbox = QCheckBox("Loại bỏ quảng cáo SponsorBlock")
        self.sponsorblock_checkbox.setChecked(self.settings.sponsorblock)

        download_layout.addLayout(format_row)
        download_layout.addWidget(self.write_subs_checkbox)
        download_layout.addWidget(self.embed_subs_checkbox)
        download_layout.addWidget(self.embed_thumb_checkbox)
        download_layout.addWidget(self.sponsorblock_checkbox)
        download_layout.addStretch(1)

        self.update_card = UpdateCard()
        self.update_info_label = self.update_card.current_label
        self.latest_version_label = self.update_card.latest_label
        self.update_status_label = self.update_card.status_label
        self.release_notes_view = self.update_card.notes
        self.check_update_button = self.update_card.check_button
        self.install_update_button = self.update_card.install_button
        self.update_progress_bar = self.update_card.progress
        self.update_progress_meta = self.update_card.progress_meta
        self.update_channel_combo = self.update_card.channel_combo
        self.update_channel_combo.setCurrentText(self.update_channel if self.update_channel in {"stable", "beta", "nightly"} else "stable")
        self.update_channel_combo.currentTextChanged.connect(self.set_update_channel)
        self.check_update_button.clicked.connect(lambda: self.check_for_updates(manual=True))
        self.install_update_button.clicked.connect(self.install_downloaded_update)
        self.update_info_label.setText(f"Phiên bản hiện tại: v{self.current_version}")
        self.latest_version_label.setText("Phiên bản mới nhất: -")
        self.update_status_label.setText("Trạng thái: -")

        storage_card = SettingsCard("Lưu trữ")
        storage_layout = storage_card.content_layout()
        storage_row = QHBoxLayout()
        self.download_dir_input = QLineEdit(self.settings.output_dir)
        self.download_dir_input.setReadOnly(True)
        self.download_dir_input.setObjectName("ReadOnlyField")
        self.change_dir_button = QPushButton("Chọn thư mục")
        self.change_dir_button.setToolTip("Chọn thư mục lưu mặc định cho video và âm thanh.")
        self.change_dir_button.clicked.connect(self.choose_download_directory)
        self.open_dir_button = QPushButton("Mở thư mục")
        self.open_dir_button.setToolTip("Mở thư mục lưu hiện tại trong trình quản lý tệp.")
        self.open_dir_button.clicked.connect(self.open_output_directory)
        storage_row.addWidget(self.download_dir_input, 1)
        storage_row.addWidget(self.change_dir_button)
        storage_row.addWidget(self.open_dir_button)
        self.disk_space_label = QLabel("Dung lượng đĩa: -")
        self.disk_space_label.setWordWrap(True)
        storage_layout.addLayout(storage_row)
        storage_layout.addWidget(self.disk_space_label)
        storage_layout.addStretch(1)

        cookie_card = SettingsCard("Cookie")
        cookie_layout = cookie_card.content_layout()
        self.cookie_mode_label = QLabel("Chế độ hiện tại: Ẩn danh")
        self.cookie_status = QLabel("Trạng thái đăng nhập: Chưa đăng nhập")
        self.cookie_status.setWordWrap(True)
        cookie_buttons = QHBoxLayout()
        self.cookie_login_button = QPushButton("Đăng nhập")
        self.cookie_login_button.setToolTip("Mở cửa sổ đăng nhập để lấy cookie tài khoản.")
        self.cookie_login_button.clicked.connect(self.open_login_dialog)
        self.cookie_logout_button = QPushButton("Đăng xuất")
        self.cookie_logout_button.setToolTip("Xóa cookie hiện tại và chuyển về chế độ ẩn danh.")
        self.cookie_logout_button.clicked.connect(self.logout_cookie)
        cookie_buttons.addWidget(self.cookie_login_button)
        cookie_buttons.addWidget(self.cookie_logout_button)
        cookie_buttons.addStretch(1)
        cookie_layout.addWidget(self.cookie_mode_label)
        cookie_layout.addWidget(self.cookie_status)
        cookie_layout.addLayout(cookie_buttons)
        cookie_layout.addStretch(1)

        grid.addWidget(download_card, 0, 0)
        grid.addWidget(self.update_card, 0, 1)
        grid.addWidget(storage_card, 1, 0)
        grid.addWidget(cookie_card, 1, 1)

        layout.addWidget(grid_host, 1)
        self.refresh_storage_status()
        self.update_cookie_status()

        return page

    def _build_logs_page(self) -> QWidget:
        page, layout = self._build_content_card("Nhật ký hệ thống")

        header = QHBoxLayout()
        header.addStretch(1)
        self.clear_button = QPushButton("Xóa nhật ký")
        self.clear_button.setObjectName("ClearButton")
        self.clear_button.clicked.connect(self.clear_log)
        header.addWidget(self.clear_button)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setObjectName("Console")

        layout.addLayout(header)
        layout.addWidget(self.console, 1)
        return page

    def _build_help_page(self) -> QWidget:
        page, layout = self._build_content_card("Hướng dẫn sử dụng")

        self.help_text = QTextBrowser()
        self.help_text.setObjectName("HelpBrowser")
        self.help_text.setOpenExternalLinks(True)
        self.help_text.setHtml(
            (
                "<div><h2 style='font-size:18px; color:#58a6ff; margin:0 0 14px 0;'>"
                "HƯỚNG DẪN SỬ DỤNG DLP Master</h2>"
                "<p style='color:#c9d1d9; line-height:1.7;'>DLP Master hỗ trợ tải video, âm thanh "
                "và playlist với hàng đợi thông minh. Ứng dụng đang chạy tối đa <b>{max_tasks}</b> "
                "tác vụ cùng lúc.</p>"
                "<ul style='color:#c9d1d9; line-height:1.7; margin:8px 0 8px 18px;'>"
                "<li>Vào tab <b>Tải xuống</b>, dán URL và nhấn <b>Bắt đầu tải</b>.</li>"
                "<li>Trong tab <b>Cài đặt</b>, chọn định dạng, thư mục lưu và kiểm tra cập nhật.</li>"
                "<li>Dùng <b>Đăng nhập tài khoản</b> để lấy cookie cho nội dung giới hạn.</li>"
                "<li>Tab <b>Nhật ký</b> hiển thị chi tiết lỗi và tiến trình xử lý.</li>"
                "</ul>"
                "<div style='border:1px solid #2f3f57; border-radius:10px; background:#121c2c; "
                "padding:12px 14px; margin:12px 0; color:#c9d1d9; line-height:1.7;'>"
                "<b>Lưu ý:</b> FFmpeg là bắt buộc cho chuyển đổi định dạng, nhúng phụ đề/thumbnail "
                "và SponsorBlock.</div>"
                "<p style='font-size:12px; color:#8b949e; margin-top:14px;'>"
                "Phiên bản hiện tại: <b>v{version}</b></p></div>"
            ).format(
                max_tasks=MAX_CONCURRENT_DOWNLOADS,
                version=VERSION,
            )
        )

        layout.addWidget(self.help_text, 1)
        return page

    def switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        if hasattr(self, "sidebar"):
            self.sidebar.set_current(index)

    def _apply_theme(self):
        apply_theme(self, "dark")

    def _start_runtime_status_timer(self):
        self.runtime_status_timer = QTimer(self)
        self.runtime_status_timer.setInterval(6000)
        self.runtime_status_timer.timeout.connect(self._poll_runtime_status)
        self.runtime_status_timer.start()
        QTimer.singleShot(500, self._poll_runtime_status)

    def _poll_runtime_status(self):
        self.network_state_text = self._probe_network_state()
        if self.network_state_text == "Offline":
            self._set_connection_chip("Mất kết nối", "error")
        elif self.connection_chip_state == "error":
            self._set_connection_chip("Sẵn sàng", "ok")
        self._refresh_runtime_status()

    @staticmethod
    def _probe_network_state() -> str:
        try:
            probe = socket.create_connection(("1.1.1.1", 53), timeout=1.2)
            probe.close()
            return "Online"
        except OSError:
            return "Offline"

    def _set_connection_chip(self, text: str, state: str):
        self.connection_chip_text = text
        self.connection_chip_state = state
        if hasattr(self, "top_header"):
            self.top_header.set_connection_status(text, state)

    def notify(self, message: str, level: str = "info"):
        if self.notifications:
            self.notifications.show(message, level=level)

    def _refresh_runtime_status(self):
        if hasattr(self, "bottom_status"):
            queued_count = len(self.pending_queue) + len(self.active_threads)
            cookie_ready = bool(self.settings.cookie_file and Path(self.settings.cookie_file).exists())
            self.bottom_status.set_metrics(queued_count, len(self.active_threads), cookie_ready, self.network_state_text)

        if hasattr(self, "top_header"):
            ffmpeg_ok = bool(FFMPEG_PATH)
            self.top_header.set_engine_status(
                "yt-dlp + FFmpeg" if ffmpeg_ok else "yt-dlp",
                "ok" if ffmpeg_ok else "warning",
            )
            self.top_header.set_connection_status(self.connection_chip_text, self.connection_chip_state)

    def set_update_status(self, state: str):
        if not hasattr(self, "update_status_label"):
            return
        if state == "uptodate":
            self.update_status_label.setText("Đã là phiên bản mới nhất")
        elif state == "available":
            self.update_status_label.setText("Có bản cập nhật")
        elif state == "failed":
            self.update_status_label.setText("Không thể cập nhật")
        else:
            self.update_status_label.setText("Trạng thái: -")

    def refresh_storage_status(self):
        if not hasattr(self, "disk_space_label"):
            return
        target = self.settings.output_dir.strip() or self.get_default_download_dir()
        try:
            usage = shutil.disk_usage(target)
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            self.disk_space_label.setText(
                f"Dung lượng đĩa: {free_gb:.1f} GB trống / {total_gb:.1f} GB tổng"
            )
        except Exception:
            self.disk_space_label.setText(
                "Dung lượng đĩa: Không thể đọc dung lượng đĩa"
            )

    def open_output_directory(self):
        target = self.settings.output_dir.strip()
        if not target:
            self.notify("Chưa có thư mục lưu.", "warning")
            return
        try:
            Path(target).mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(target)
            else:
                webbrowser.open(target)
        except Exception as err:
            self.notify(
                "Không thể mở thư mục: {error}".format(error=clean_log_text(err)),
                "error",
            )

    def logout_cookie(self):
        cookie_file = self.settings.cookie_file
        self.settings.cookie_file = ""
        if cookie_file and Path(cookie_file).exists():
            try:
                Path(cookie_file).unlink()
            except OSError:
                pass
        self.update_cookie_status()
        self.notify("Đã đăng xuất cookie.", "info")

    def parse_urls(self, raw: str) -> list[str]:
        normalized = raw.replace(",", "\n")
        parts = [line.strip() for line in normalized.splitlines()]
        return [part for part in parts if part]

    def add_queue_item(self, task: DownloadTask):
        row = QueueRowState(
            task_id=task.task_id,
            url=task.url,
            title=task.url,
            status="Queued",
            format_label=self.settings.output_format,
        )
        self.queue_rows[task.task_id] = row
        self.queue_table.add_row(
            task.task_id,
            [row.status, row.title, row.progress, row.speed, row.eta, row.size, row.format_label],
        )

    def _update_queue_row(self, task_id: str):
        row = self.queue_rows.get(task_id)
        if not row:
            return
        status_map = {
            "Queued": "Đang chờ",
            "Running": "Đang tải",
            "Post-processing": "Đang xử lý",
            "Done": "Hoàn tất",
            "Failed": "Thất bại",
            "Paused": "Đã dừng",
        }
        self.queue_table.update_row(
            task_id,
            [status_map.get(row.status, row.status), row.title, row.progress, row.speed, row.eta, row.size, row.format_label],
        )

    @staticmethod
    def _extract_speed_eta(details: str) -> tuple[str, str]:
        speed = "-"
        eta = "-"
        parts = [part.strip() for part in str(details or "").split("|")]
        if len(parts) >= 2 and parts[1]:
            speed = parts[1]
        if len(parts) >= 3:
            eta_part = parts[2]
            if eta_part.lower().startswith("eta"):
                eta = eta_part.split(" ", 1)[-1].strip() or "-"
        return speed, eta

    def enqueue_from_input(self):
        self.apply_settings_from_controls()
        raw = self.url_input.text().strip()
        if not raw:
            self.notify("Thiếu URL: Hãy dán URL cần tải.", "warning")
            return

        urls = self.parse_urls(raw)
        if not urls:
            self.notify("URL không hợp lệ: Không tìm thấy URL trong ô nhập.", "warning")
            return

        output_dir = self.output_path_input.text().strip()
        if not output_dir:
            self.notify("Thư mục lưu không hợp lệ. Hãy chọn thư mục trước khi tải.", "warning")
            return
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except OSError as err:
            self.notify("Không thể tạo/ghi vào thư mục đã chọn: {error}".format(error=err), "error")
            return
        self.settings.output_dir = output_dir

        if not FFMPEG_PATH and self.settings_requires_ffmpeg():
            self.notify(
                "Thiếu FFmpeg: cấu hình hiện tại cần FFmpeg để chuyển đổi/xử lý media.",
                "error",
            )
            return

        for url in urls:
            task = DownloadTask(task_id=uuid.uuid4().hex[:8], url=url)
            self.pending_queue.append(task)
            self.add_queue_item(task)
            self.append_log("info", "[hàng đợi] Đã thêm {task_id}: {url}".format(task_id=task.task_id, url=url))

        self.url_input.clear()
        self._refresh_runtime_status()
        self.pump_queue()

    def apply_settings_from_controls(self):
        self.settings.output_format = self.format_combo.currentText()
        self.settings.write_subs = self.write_subs_checkbox.isChecked()
        self.settings.embed_subs_checkbox = self.embed_subs_checkbox.isChecked()
        self.settings.embed_thumbnail = self.embed_thumb_checkbox.isChecked()
        self.settings.sponsorblock = self.sponsorblock_checkbox.isChecked()

    def settings_requires_ffmpeg(self) -> bool:
        return (
            self.settings.output_format in {"MP4", "MP4 (Convert)", "MKV", "MP3", "FLAC"}
            or self.settings.write_subs
            or self.settings.embed_subs_checkbox
            or self.settings.embed_thumbnail
            or self.settings.sponsorblock
        )

    def pump_queue(self):
        while self.pending_queue and len(self.active_threads) < MAX_CONCURRENT_DOWNLOADS:
            task = self.pending_queue.popleft()
            self.start_task(task)
        self._refresh_runtime_status()

    def start_task(self, task: DownloadTask):
        row = self.queue_rows.get(task.task_id)
        if row:
            row.status = "Running"
            row.details = "Khoi tao worker"
            self._update_queue_row(task.task_id)

        thread = QThread()
        worker = DownloadWorker(task, self.settings)
        worker.moveToThread(thread)

        worker.signals.log.connect(self.append_log)
        worker.signals.metadata.connect(self.handle_task_metadata)
        worker.signals.progress.connect(self.handle_task_progress)
        worker.signals.finished.connect(self.handle_task_finished)

        thread.started.connect(worker.run)
        worker.signals.finished.connect(thread.quit)
        worker.signals.finished.connect(worker.deleteLater)
        
        # CHỈ GỌI hàm dọn dẹp dữ liệu KHI thread phát tín hiệu đã ngắt hoàn toàn
        thread.finished.connect(lambda task_id=task.task_id: self.handle_thread_finished(task_id))
        thread.finished.connect(thread.deleteLater)

        self.active_threads[task.task_id] = (thread, worker)
        self.append_log("warning", "[hàng đợi] Bắt đầu tác vụ {task_id}".format(task_id=task.task_id))
        thread.start()
        self._refresh_runtime_status()

    def handle_task_metadata(self, task_id: str, title: str, size_hint: str):
        row = self.queue_rows.get(task_id)
        if not row:
            return
        row.title = title
        if size_hint and size_hint != "-":
            row.size = size_hint
        self._update_queue_row(task_id)

    def handle_task_progress(self, task_id: str, percent: int, size_text: str, details: str):
        row = self.queue_rows.get(task_id)
        if not row:
            return
        speed, eta = self._extract_speed_eta(details)
        row.progress = f"{max(0, min(100, int(percent)))}%"
        row.speed = speed
        row.eta = eta
        row.size = size_text or row.size
        row.status = "Running" if percent < 100 else "Post-processing"
        row.details = details
        self._update_queue_row(task_id)

    def handle_task_finished(self, task_id: str, ok: bool, message: str):
        row = self.queue_rows.get(task_id)
        if row:
            cancelled = "đã dừng bởi người dùng" in clean_log_text(message).lower()
            if ok:
                row.status = "Done"
                row.progress = "100%"
                if row.size == "-":
                    row.size = row.details.split("|")[0].strip() if row.details and "|" in row.details else row.size
                row.eta = "00:00"
            elif cancelled:
                row.status = "Paused"
            else:
                row.status = "Failed"
            self._update_queue_row(task_id)

        level = "success" if ok else "error"
        prefix = "[done]" if ok else "[failed]"
        self.append_log(level, f"{prefix} {task_id}: {clean_log_text(message)}")

    def handle_thread_finished(self, task_id: str):
        timer = self.force_stop_timers.pop(task_id, None)
        if timer:
            timer.stop()
            timer.deleteLater()
        self.active_threads.pop(task_id, None)
        self._refresh_runtime_status()
        self.pump_queue()

    def update_cookie_status(self):
        has_cookie = bool(self.settings.cookie_file and Path(self.settings.cookie_file).exists())
        if has_cookie:
            self.cookie_status.setText(
                f"Trạng thái đăng nhập: Đã đăng nhập ({self.settings.cookie_file})"
            )
            if hasattr(self, "cookie_mode_label"):
                self.cookie_mode_label.setText(
                    "Chế độ hiện tại: Cookie tài khoản"
                )
        else:
            self.cookie_status.setText(
                "Trạng thái đăng nhập: Chưa đăng nhập"
            )
            if hasattr(self, "cookie_mode_label"):
                self.cookie_mode_label.setText(
                    "Chế độ hiện tại: Ẩn danh"
                )
        self._refresh_runtime_status()

    def set_update_channel(self, channel: str):
        self.update_channel = (channel or "stable").strip().lower()
        self.append_log("info", "[cập nhật] Kênh cập nhật: {channel}".format(channel=self.update_channel))

    def check_for_updates_silent(self):
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual: bool = False):
        if not self.update_url:
            self.append_log("warning", "[cập nhật] Chưa cấu hình UPDATE_URL trong app_config.py")
            self.set_update_status("failed")
            return
        if self.update_check_thread and self.update_check_thread.isRunning():
            return

        if manual:
            self.append_log("info", "[cập nhật] Đang kiểm tra cập nhật...")
        self.check_update_button.setEnabled(False)
        self.update_check_thread = UpdateCheckThread(
            self.update_url,
            self.current_version,
            CONFIG_APP_NAME,
            self.update_channel,
        )
        self.update_check_thread.update_checked.connect(lambda ok, result, message, manual=manual: self.on_update_check_completed(ok, result, message, manual))
        self.update_check_thread.finished.connect(self.update_check_thread.deleteLater)
        self.update_check_thread.finished.connect(self._clear_update_check_thread)
        self.update_check_thread.start()

    def _clear_update_check_thread(self):
        self.update_check_thread = None
        if hasattr(self, "check_update_button"):
            self.check_update_button.setEnabled(True)

    def on_update_check_completed(self, success: bool, result: UpdateCheckResult | None, message: str, manual: bool):
        if not success or not result:
            self.append_log("warning", "[cập nhật] Không thể kiểm tra cập nhật: {error}".format(error=clean_log_text(message)))
            self.set_update_status("failed")
            if hasattr(self, "top_header"):
                self._set_connection_chip("Cập nhật thất bại", "error")
            if manual and hasattr(self, "release_notes_view"):
                self.release_notes_view.setPlainText(
                    "Lỗi cập nhật: {message}".format(message=clean_log_text(message))
                )
            return

        self.pending_update_result = result
        manifest = result.manifest
        self.latest_release_url = manifest.download_url
        if hasattr(self, "latest_version_label"):
            self.latest_version_label.setText(f"Phiên bản mới nhất: v{result.latest_version}")
        if hasattr(self, "release_notes_view"):
            self.release_notes_view.setPlainText(simplify_release_notes(result.latest_version, manifest.release_notes or ""))

        if not result.is_supported:
            self.append_log("warning", "[cập nhật] Phiên bản hiện tại thấp hơn minimum_version v{version}.".format(version=manifest.minimum_version))

        if result.update_available:
            self.set_update_status("available")
            if hasattr(self, "top_header"):
                self._set_connection_chip("Có bản cập nhật", "warning")
            self.append_log(
                "warning",
                "[cập nhật] Có phiên bản mới v{latest} (hiện tại v{current}).".format(latest=result.latest_version, current=result.current_version),
            )
            if result.latest_version == self.skipped_update_version:
                return
            if manual or self.update_prompted_version != result.latest_version:
                self.update_prompted_version = result.latest_version
                self.show_update_dialog(result)
        elif manual:
            self.set_update_status("uptodate")
            if hasattr(self, "top_header"):
                self._set_connection_chip("Đã là phiên bản mới nhất", "ok")
            self.append_log("success", "[cập nhật] Đang ở phiên bản mới nhất: v{version}".format(version=self.current_version))

    def show_update_dialog(self, result: UpdateCheckResult):
        dialog = UpdateDialog(result.current_version, result.latest_version, result.manifest.release_notes, self)
        dialog.skip_button.clicked.connect(lambda: self.skip_update_version(result.latest_version))
        dialog.later_button.clicked.connect(dialog.close)
        dialog.download_button.clicked.connect(lambda: self.start_update_download(result.manifest))
        dialog.install_button.clicked.connect(self.install_downloaded_update)
        dialog.cancel_button.clicked.connect(self.cancel_update_download)
        self.update_dialog = dialog
        dialog.show()

    def skip_update_version(self, version: str):
        self.skipped_update_version = version
        self.append_log("info", "[cập nhật] Đã bỏ qua phiên bản v{version}".format(version=version))
        if self.update_dialog:
            self.update_dialog.close()

    def start_update_download(self, manifest):
        if self.update_download_thread and self.update_download_thread.isRunning():
            return
        target_dir = Path(tempfile.gettempdir()) / "dlp-master-updates"
        self.downloaded_update_package = ""
        if self.update_dialog:
            self.update_dialog.set_download_running(True)
            self.update_dialog.set_progress(0, "Đang tải bản cập nhật...")
        if hasattr(self, "update_progress_bar"):
            self.update_progress_bar.setValue(0)
        if hasattr(self, "update_progress_meta"):
            self.update_progress_meta.setText("Đã tải: 0% | Tốc độ: - | Thời gian còn lại: -")

        self.update_download_thread = UpdateDownloadThread(
            manifest,
            str(target_dir),
            CONFIG_APP_NAME,
            {
                "cancelled": "Đã hủy tải cập nhật",
                "sha_failed": "Xác minh SHA256 thất bại",
                "verified": "Đã xác minh tải cập nhật",
            },
        )
        self.update_download_thread.download_progress.connect(self.on_update_download_progress)
        self.update_download_thread.download_finished.connect(self.on_update_download_finished)
        self.update_download_thread.finished.connect(self.update_download_thread.deleteLater)
        self.update_download_thread.finished.connect(self._clear_update_download_thread)
        self.update_download_thread.start()

    def on_update_download_progress(self, percent: int, status: str):
        if self.update_dialog:
            self.update_dialog.set_progress(percent, status)
        if hasattr(self, "update_progress_bar"):
            self.update_progress_bar.setValue(max(0, min(int(percent), 100)))
        if hasattr(self, "update_progress_meta"):
            self.update_progress_meta.setText(
                "Đã tải: {percent}% | {status}".format(percent=percent, status=status)
            )

    def on_update_download_finished(self, success: bool, package_path: str, message: str):
        if success:
            self.downloaded_update_package = package_path
            self.append_log("success", "[cập nhật] Đã tải và xác minh SHA256: {path}".format(path=package_path))
            self.set_update_status("available")
            if hasattr(self, "install_update_button"):
                self.install_update_button.setEnabled(True)
            if self.update_dialog:
                self.update_dialog.set_progress(100, "Đã tải xong và xác minh SHA256. Sẵn sàng cài đặt.")
                self.update_dialog.set_ready_to_install(True)
        else:
            self.append_log("warning", "[cập nhật] Tải cập nhật thất bại: {error}".format(error=clean_log_text(message)))
            self.set_update_status("failed")
            if self.update_dialog:
                self.update_dialog.set_progress(0, "Tải cập nhật thất bại: {message}".format(message=clean_log_text(message)))
                self.update_dialog.set_download_running(False)

    def _clear_update_download_thread(self):
        self.update_download_thread = None

    def cancel_update_download(self):
        if self.update_download_thread and self.update_download_thread.isRunning():
            self.update_download_thread.cancel()
            self.append_log("warning", "[cập nhật] Đang hủy tải cập nhật...")

    def install_downloaded_update(self):
        if not self.downloaded_update_package:
            self.append_log("warning", "[cập nhật] Chưa có gói cập nhật đã tải.")
            return
        if self.active_threads:
            self.append_log("warning", "[cập nhật] Hãy dừng hoặc đợi các tác vụ tải hoàn tất trước khi cài cập nhật.")
            return
        try:
            launch_updater(self.downloaded_update_package, app_root(), restart=True)
        except Exception as err:
            self.append_log("error", "[cập nhật] Không thể mở updater: {error}".format(error=clean_log_text(err)))
            return

        self.append_log("success", "[cập nhật] Đã mở DLP Master Updater. Ứng dụng chính sẽ đóng để cài cập nhật.")
        if self.update_dialog:
            self.update_dialog.close()
        QTimer.singleShot(250, QApplication.instance().quit)

    def open_login_dialog(self):
        if not WEBENGINE_AVAILABLE:
            self.append_log("warning", "[đăng nhập] Qt WebEngine chưa sẵn sàng. Cài đặt thêm: pip install PyQt6-WebEngine")
            return

        old_cookie = self.settings.cookie_file
        try:
            dialog = EmbeddedLoginDialog(self)
            dialog.setStyleSheet(self.styleSheet())
            dialog.exec()
        except Exception as err:
            self.notify("Không thể mở cửa sổ đăng nhập: {error}".format(error=err), "error")
            return

        new_cookie_file = dialog.cookie_file_path
        if new_cookie_file and Path(new_cookie_file).exists():
            self.settings.cookie_file = new_cookie_file
            if old_cookie and Path(old_cookie).exists() and old_cookie != new_cookie_file:
                try:
                    Path(old_cookie).unlink()
                except OSError:
                    pass
            self.update_cookie_status()
            self.append_log("info", "[cài đặt] Đăng nhập nhúng thành công, đã cập nhật cookie tạm")

    def choose_download_directory(self):
        current_dir = self.settings.output_dir.strip() or self.get_default_download_dir()
        selected_dir = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu video/âm thanh", current_dir)
        if selected_dir:
            if hasattr(self, "download_dir_input"):
                self.download_dir_input.setText(selected_dir)
            if hasattr(self, "output_path_input"):
                self.output_path_input.setText(selected_dir)
            self.settings.output_dir = selected_dir
            self.append_log("info", "[cài đặt] Thư mục lưu mới: {path}".format(path=selected_dir))
            self.refresh_storage_status()

    def append_log(self, level: str, message: str):
        colors = {"success": "#7cf2bf", "warning": "#ffd166", "error": "#ff7f7f", "info": "#dbe4ee"}
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors.get(level, "#dbe4ee")))
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(clean_log_text(message) + "\n", fmt)
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def clear_log(self):
        self.console.clear()
        self.append_log("info", "Nhật ký đã được xóa.")

    def clear_completed_items(self):
        removed = 0
        for task_id, row in list(self.queue_rows.items()):
            if task_id in self.active_threads:
                continue
            if row.status not in {"Done", "Failed", "Paused"}:
                continue
            self.queue_table.remove_row_by_task_id(task_id)
            del self.queue_rows[task_id]
            removed += 1
        if removed:
            self.append_log("info", "[hàng đợi] Đã xóa {count} mục".format(count=removed))
        self._refresh_runtime_status()

    def stop_all_tasks(self):
        self.pending_queue.clear()
        for task_id, row in self.queue_rows.items():
            if task_id not in self.active_threads and row.status == "Queued":
                row.status = "Paused"
                self._update_queue_row(task_id)

        for task_id, (thread, worker) in list(self.active_threads.items()):
            worker.stop()
            if task_id not in self.force_stop_timers:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda task_id=task_id: self.force_terminate_task(task_id))
                timer.start(3000)
                self.force_stop_timers[task_id] = timer
            self._refresh_runtime_status()

    def pause_selected_task(self, task_id: str):
        if not task_id:
            self.notify("Hãy chọn một tác vụ trong bảng hàng đợi.", "warning")
            return
        pair = self.active_threads.get(task_id)
        if pair:
            _thread, worker = pair
            worker.stop()
            self.append_log("warning", "[hàng đợi] Tạm dừng tác vụ {task_id}".format(task_id=task_id))
            return
        row = self.queue_rows.get(task_id)
        if row and row.status == "Queued":
            row.status = "Paused"
            self._update_queue_row(task_id)

    def resume_selected_task(self, task_id: str):
        if not task_id:
            self.notify("Hãy chọn một tác vụ trong bảng hàng đợi.", "warning")
            return
        row = self.queue_rows.get(task_id)
        if not row:
            return
        if row.status != "Paused":
            self.notify("Tác vụ này không ở trạng thái tạm dừng.", "warning")
            return
        retry_task = DownloadTask(task_id=uuid.uuid4().hex[:8], url=row.url)
        self.pending_queue.appendleft(retry_task)
        self.add_queue_item(retry_task)
        self.queue_table.remove_row_by_task_id(task_id)
        del self.queue_rows[task_id]
        self.pump_queue()

    def retry_selected_task(self, task_id: str):
        if not task_id:
            self.notify("Hãy chọn một tác vụ trong bảng hàng đợi.", "warning")
            return
        if task_id in self.active_threads:
            self.notify("Tác vụ đang chạy, chưa thể tải lại ngay.", "warning")
            return
        row = self.queue_rows.get(task_id)
        if not row:
            return
        retry_task = DownloadTask(task_id=uuid.uuid4().hex[:8], url=row.url)
        self.pending_queue.append(retry_task)
        self.add_queue_item(retry_task)
        self.append_log("info", "[hàng đợi] Tải lại từ tác vụ {from_task} -> {to_task}".format(from_task=task_id, to_task=retry_task.task_id))
        self.pump_queue()

    def delete_selected_task(self, task_id: str):
        if not task_id:
            self.notify("Hãy chọn một tác vụ trong bảng hàng đợi.", "warning")
            return
        if task_id in self.active_threads:
            self.notify("Không thể xóa tác vụ đang chạy.", "warning")
            return
        self.pending_queue = deque([task for task in self.pending_queue if task.task_id != task_id])
        self.queue_table.remove_row_by_task_id(task_id)
        if task_id in self.queue_rows:
            del self.queue_rows[task_id]
        self._refresh_runtime_status()

    def force_terminate_task(self, task_id: str):
        pair = self.active_threads.get(task_id)
        if not pair:
            return
        thread, worker = pair
        if not thread.isRunning():
            return
        worker.emit_cancelled_once()
        thread.terminate()
        thread.wait(1000)

    def closeEvent(self, event):
        if self.active_threads:
            self.notify("Hãy đợi hoàn tất hoặc dừng các tác vụ trước khi đóng ứng dụng.", "warning")
            event.ignore()
            return

        if self.settings.cookie_file and Path(self.settings.cookie_file).exists():
            try:
                Path(self.settings.cookie_file).unlink()
            except OSError:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    global APP_INSTANCE_LOCK
    lock_path = os.path.join(tempfile.gettempdir(), "dlp_master_qt.lock")
    APP_INSTANCE_LOCK = QLockFile(lock_path)
    APP_INSTANCE_LOCK.setStaleLockTime(0)
    if not APP_INSTANCE_LOCK.tryLock(100):
        print("DLP Master dang chay o cua so khac.")
        return

    window = MainWindow()
    window.show()
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        exit_code = 0
    finally:
        if APP_INSTANCE_LOCK and APP_INSTANCE_LOCK.isLocked():
            APP_INSTANCE_LOCK.unlock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
