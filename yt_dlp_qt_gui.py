from __future__ import annotations

import os
import re
import json
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
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
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
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
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
            # SỬA DÒNG NÀY: Giới hạn tiêu đề video lấy tối đa 100 ký tự để tránh lỗi quá dài
            "outtmpl": os.path.join(target_dir, "%(title).100s.%(ext)s"),
            "logger": QtYtDlpLogger(self.signals, self.task.task_id, is_cancelled=self.stop_event.is_set),
            "progress_hooks": [self.progress_hook],
            
            # BỔ SUNG 2 DÒNG NÀY: Ép buộc tên file tuân thủ quy tắc Windows và loại bỏ ký tự lạ ASCII
            "windowsfilenames": True,
            "restrictfilenames": True,  # Loại bỏ khoảng trắng phức tạp, dấu tiếng Việt và ký tự đặc biệt gây lỗi
            
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
            f"Đang đăng nhập {self.selected_platform}. Sau khi xong, đóng cửa sổ để lưu cookie tự động."
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
        self.info_label.setText(f"Đã ghi nhận {len(self.cookies)} cookie. Có thể đóng cửa sổ khi đăng nhập xong.")
        self.maybe_auto_close_on_login(record)

    def on_cookie_removed(self, cookie):
        record = self.to_record(cookie)
        if not record:
            return
        key = (record.domain, record.path, record.name)
        if key in self.cookies:
            del self.cookies[key]
        self.info_label.setText(f"Đã ghi nhận {len(self.cookies)} cookie. Có thể đóng cửa sổ khi đăng nhập xong.")

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
            f"Đăng nhập {self.selected_platform} thành công. Cửa sổ sẽ tự động đóng..."
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
            QMessageBox.warning(
                self,
                "Chưa thấy cookie đăng nhập",
                (
                    f"Chưa phát hiện cookie đăng nhập hợp lệ cho {self.selected_platform}.\n"
                    "Bạn hãy đăng nhập xong, đợi trang tải lại rồi bấm nút này lần nữa."
                ),
            )
            self.info_label.setText(
                f"Đã ghi nhận {len(self.cookies)} cookie tổng, {platform_count} cookie nền tảng, {auth_count} cookie đăng nhập."
            )
            return

        self.auth_verified = True
        self.info_label.setText(
            f"Xác nhận đăng nhập {self.selected_platform} thành công ({auth_count} cookie đăng nhập). Đang lưu cookie..."
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
            "# This file was generated by embedded Qt WebEngine login\n",
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

        format_label = QLabel("Định dạng đầu ra")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MP4 (Convert)", "MKV", "MP3", "FLAC"])
        self.format_combo.setCurrentText(current.output_format)

        self.write_subs = QCheckBox("Tải xuống phụ đề")
        self.write_subs.setChecked(current.write_subs)

        self.embed_subs_checkbox = QCheckBox("Nhúng phụ đề vào video")
        self.embed_subs_checkbox.setChecked(current.embed_subs_checkbox)

        self.embed_thumb = QCheckBox("Nhúng thumbnail vào file")
        self.embed_thumb.setChecked(current.embed_thumbnail)

        self.sponsorblock = QCheckBox("Cắt quảng cáo với SponsorBlock")
        self.sponsorblock.setChecked(current.sponsorblock)

        self.login_button = QPushButton("🔑 Đăng nhập tài khoản để tải video giới hạn")
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
            self.cookie_status.setText("Qt WebEngine chưa sẵn sàng. Cài: pip install PyQt6-WebEngine")

    def update_cookie_status(self):
        if self.cookie_file_path and Path(self.cookie_file_path).exists():
            self.cookie_status.setText(f"Cookie đang sử dụng: {self.cookie_file_path}")
        else:
            self.cookie_status.setText("Cookie mode: Public/Ẩn danh (chưa đăng nhập)")

    def open_login_dialog(self):
        if not WEBENGINE_AVAILABLE:
            QMessageBox.warning(self, "Thiếu WebEngine", "Cài đặt thêm: pip install PyQt6-WebEngine")
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
            QMessageBox.information(self, "Cookie", "Chưa thu được cookie nào. Hãy đăng nhập rồi đóng cửa sổ trình duyệt.")

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
                message = output or "yt-dlp da duoc cap nhat thanh cong."
                self.update_finished.emit(True, message)
            else:
                message = output or f"pip ket thuc voi ma loi {result.returncode}."
                self.update_finished.emit(False, message)
        except Exception as exc:
            self.update_finished.emit(False, f"Loi khi cap nhat yt-dlp: {exc}")


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

    def __init__(self, manifest, target_dir: str, app_name: str):
        super().__init__()
        self.manifest = manifest
        self.target_dir = target_dir
        self.app_name = app_name
        self._cancelled = False

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
                self.download_finished.emit(False, "", "Download cancelled")
                return
            if not verify_sha256(package_path, self.manifest.sha256):
                self.download_finished.emit(False, "", "SHA256 verification failed")
                return
            self.download_finished.emit(True, str(package_path), "Download verified")
        except DownloadCancelled as exc:
            self.download_finished.emit(False, "", str(exc))
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
        self.queue_widgets: dict[str, QueueItemWidget] = {}
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

        self.setWindowTitle("yt-dlp Queue Downloader")
        self.resize(1280, 780)
        self.setMinimumSize(1040, 680)
        self._build_ui()
        self._apply_theme()

        self.append_log("success", "[hệ thống] Dashboard sẵn sàng.")
        if FFMPEG_PATH:
            self.append_log("success", f"[system] ffmpeg: {FFMPEG_PATH}")
        else:
            self.append_log("warning", "[hệ thống] Không tìm thấy ffmpeg. Các chế độ chuyển định dạng video/audio sẽ thất bại.")

        if WEBENGINE_AVAILABLE:
            self.append_log("info", "[hệ thống] Qt WebEngine sẵn sàng cho đăng nhập nhúng.")
        else:
            self.append_log("warning", "[hệ thống] Chưa có Qt WebEngine. Cài PyQt6-WebEngine để dùng đăng nhập nhúng.")
        self.append_log("info", f"[hệ thống] Phiên bản ứng dụng: v{self.current_version}")
        self.append_log("info", f"[hệ thống] Thư mục lưu mặc định: {self.settings.output_dir}")
        self.update_cookie_status()
        QTimer.singleShot(1500, self.check_for_updates_silent)
        if self.is_frozen_build:
            self.append_log("info", "[system] Bo qua auto-cap nhat yt-dlp bang pip trong ban dong goi (.exe).")
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
        self.append_log("info", "[system] Dang kiem tra va nang cap yt-dlp trong nen...")
        self.update_thread = UpdateThread()
        self.update_thread.update_finished.connect(self.on_update_completed)
        self.update_thread.finished.connect(self._clear_update_thread)
        self.update_thread.finished.connect(self.update_thread.deleteLater)
        self.update_thread.start()

    def on_update_completed(self, success, message):
        level = "success" if success else "warning"
        prefix = "[system] Cap nhat yt-dlp hoan tat" if success else "[system] Cap nhat yt-dlp that bai"
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

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 14)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel("⚡ DLPMaster")
        sidebar_title.setObjectName("SidebarTitle")
        sidebar_layout.addWidget(sidebar_title)

        self.btn_download_page = QPushButton("📥 Tiến trình tải")
        self.btn_settings_page = QPushButton("⚙️ Cấu hình & Cookie")
        self.btn_logs_page = QPushButton("📄 Nhật ký hệ thống")
        self.btn_help_page = QPushButton("❓ Hướng dẫn sử dụng")
        self.sidebar_buttons = [
            self.btn_download_page,
            self.btn_settings_page,
            self.btn_logs_page,
            self.btn_help_page,
        ]
        for index, button in enumerate(self.sidebar_buttons):
            button.setCheckable(True)
            button.setObjectName("SidebarButton")
            button.clicked.connect(lambda _checked, idx=index: self.switch_page(idx))
            sidebar_layout.addWidget(button)

        sidebar_layout.addSpacing(10)
        self.sidebar_login_button = QPushButton("🔑 Đăng nhập tài khoản")
        self.sidebar_login_button.setObjectName("SidebarActionButton")
        self.sidebar_login_button.clicked.connect(self.open_login_dialog)
        sidebar_layout.addWidget(self.sidebar_login_button)
        sidebar_layout.addStretch(1)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")
        self.stack.addWidget(self._build_download_page())
        self.stack.addWidget(self._build_settings_page())
        self.stack.addWidget(self._build_logs_page())
        self.stack.addWidget(self._build_help_page())

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.switch_page(0)

    def _build_content_card(self, title_text: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ContentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        title = QLabel(title_text)
        title.setObjectName("SectionTitle")
        card_layout.addWidget(title)

        page_layout.addWidget(card)
        return page, card_layout

    def _build_download_page(self) -> QWidget:
        page, layout = self._build_content_card("Tiến trình tải")

        url_row = QHBoxLayout()
        url_row.setSpacing(10)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Dán một hoặc nhiều URL (mỗi dòng một link)")
        self.url_input.setMinimumHeight(42)
        self.url_input.returnPressed.connect(self.enqueue_from_input)

        self.download_button = QPushButton("BẮT ĐẦU TẢI")
        self.download_button.setObjectName("StartButton")
        self.download_button.setMinimumHeight(42)
        self.download_button.clicked.connect(self.enqueue_from_input)

        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.download_button)

        queue_container = QFrame()
        queue_container.setObjectName("QueueContainer")
        queue_layout = QVBoxLayout(queue_container)
        queue_layout.setContentsMargins(12, 12, 12, 12)
        queue_layout.setSpacing(10)

        queue_header = QHBoxLayout()
        queue_title = QLabel("Hàng đợi tải")
        queue_title.setObjectName("SectionTitle")

        self.stop_all_button = QPushButton("Dừng tất cả")
        self.stop_all_button.setObjectName("QueueDangerButton")
        self.stop_all_button.clicked.connect(self.stop_all_tasks)

        self.clear_completed_button = QPushButton("Xóa danh sách")
        self.clear_completed_button.setObjectName("QueueActionButton")
        self.clear_completed_button.clicked.connect(self.clear_completed_items)

        queue_header.addWidget(queue_title)
        queue_header.addStretch(1)
        queue_header.addWidget(self.stop_all_button)
        queue_header.addWidget(self.clear_completed_button)

        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setObjectName("QueueScroll")
        self.queue_holder = QWidget()
        self.queue_items_layout = QVBoxLayout(self.queue_holder)
        self.queue_items_layout.setContentsMargins(2, 2, 2, 2)
        self.queue_items_layout.setSpacing(8)
        self.queue_items_layout.addStretch(1)
        self.queue_scroll.setWidget(self.queue_holder)

        queue_layout.addLayout(queue_header)
        queue_layout.addWidget(self.queue_scroll, 1)

        layout.addLayout(url_row)
        layout.addWidget(queue_container, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._build_content_card("Cấu hình & Cookie")

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        format_label = QLabel("Định dạng")
        format_label.setObjectName("Hint")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MP4 (Convert)", "MKV", "MP3", "FLAC"])
        self.format_combo.setCurrentText(self.settings.output_format)
        row1.addWidget(format_label)
        row1.addWidget(self.format_combo, 1)

        self.embed_subs = QCheckBox("Tự động nhúng phụ đề")
        self.embed_subs.setChecked(self.settings.embed_subs_checkbox)
        self.embed_thumb = QCheckBox("Nhúng thumbnail vào file")
        self.embed_thumb.setChecked(self.settings.embed_thumbnail)
        self.sponsorblock = QCheckBox("Cắt quảng cáo với SponsorBlock")
        self.sponsorblock.setChecked(self.settings.sponsorblock)

        folder_row = QHBoxLayout()
        folder_label = QLabel("Thư mục lưu:")
        folder_label.setObjectName("Hint")
        self.download_dir_input = QLineEdit(self.settings.output_dir)
        self.download_dir_input.setReadOnly(True)
        self.download_dir_input.setObjectName("ReadOnlyField")
        self.change_dir_button = QPushButton("Thay đổi...")
        self.change_dir_button.setObjectName("SettingsButton")
        self.change_dir_button.clicked.connect(self.choose_download_directory)
        folder_row.addWidget(folder_label)
        folder_row.addWidget(self.download_dir_input, 1)
        folder_row.addWidget(self.change_dir_button)

        self.cookie_status = QLabel()
        self.cookie_status.setObjectName("Hint")
        self.cookie_status.setWordWrap(True)

        self.write_subs_checkbox = QCheckBox("Tải xuống phụ đề")
        self.write_subs_checkbox.setChecked(self.settings.write_subs)

        self.embed_subs_checkbox = QCheckBox("Nhúng phụ đề vào video")
        self.embed_subs_checkbox.setChecked(self.settings.embed_subs_checkbox)

        self.embed_thumb_checkbox = QCheckBox("Nhúng thumbnail vào file")
        self.embed_thumb_checkbox.setChecked(self.settings.embed_thumbnail)

        self.sponsorblock_checkbox = QCheckBox("Cắt quảng cáo với SponsorBlock")
        self.sponsorblock_checkbox.setChecked(self.settings.sponsorblock)

        channel_row = QHBoxLayout()
        channel_label = QLabel("Update Channel")
        channel_label.setObjectName("Hint")
        self.update_channel_combo = QComboBox()
        self.update_channel_combo.addItems(["stable", "beta", "nightly"])
        self.update_channel_combo.setCurrentText(self.update_channel if self.update_channel in {"stable", "beta", "nightly"} else "stable")
        self.update_channel_combo.currentTextChanged.connect(self.set_update_channel)
        channel_row.addWidget(channel_label)
        channel_row.addWidget(self.update_channel_combo, 1)

        update_row = QHBoxLayout()
        self.update_info_label = QLabel(f"Phiên bản hiện tại: v{self.current_version}")
        self.update_info_label.setObjectName("Hint")
        self.latest_version_label = QLabel("Latest Version: -")
        self.latest_version_label.setObjectName("Hint")
        self.check_update_button = QPushButton("Kiểm tra cập nhật")
        self.check_update_button.setObjectName("SettingsButton")
        self.check_update_button.clicked.connect(lambda: self.check_for_updates(manual=True))
        update_row.addWidget(self.update_info_label)
        update_row.addWidget(self.latest_version_label)
        update_row.addStretch(1)
        update_row.addWidget(self.check_update_button)

        self.release_notes_view = QTextBrowser()
        self.release_notes_view.setObjectName("HelpBrowser")
        self.release_notes_view.setReadOnly(True)
        self.release_notes_view.setMaximumHeight(120)
        self.release_notes_view.setPlainText("Release Notes: -")

        layout.addLayout(row1)
        layout.addWidget(self.write_subs_checkbox)
        layout.addWidget(self.embed_subs_checkbox)
        layout.addWidget(self.embed_thumb_checkbox)
        layout.addWidget(self.sponsorblock_checkbox)
        layout.addLayout(channel_row)
        layout.addLayout(update_row)
        layout.addWidget(self.release_notes_view)
        layout.addLayout(folder_row)
        layout.addWidget(self.cookie_status)
        layout.addStretch(1)

        return page

    def _build_logs_page(self) -> QWidget:
        page, layout = self._build_content_card("Nhật ký hệ thống")

        header = QHBoxLayout()
        header.addStretch(1)
        self.clear_button = QPushButton("Xóa log")
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
            f"""
            <div>
                <h2 style='font-size:18px; color:#58a6ff; margin:0 0 14px 0;'>HƯỚNG DẪN SỬ DỤNG DLP-Master</h2>

                <h3 style='font-size:14px; color:#eac54f; margin:14px 0 8px 0; font-weight:700;'>1) TỔNG QUAN GIAO DIỆN</h3>
                <ul style='color:#c9d1d9; line-height:1.7; margin:0 0 8px 18px;'>
                    <li><b>Tiến trình tải</b>: dán link, bắt đầu tải, theo dõi tiến độ và trạng thái từng video.</li>
                    <li><b>Cấu hình &amp; Cookie</b>: chọn định dạng xuất, phụ đề, thumbnail, SponsorBlock, thư mục lưu và kiểm tra cập nhật ứng dụng.</li>
                    <li><b>Nhật ký hệ thống</b>: xem log chi tiết của yt-dlp, ffmpeg, cookie, cập nhật và lỗi phát sinh.</li>
                    <li><b>Hướng dẫn sử dụng</b>: xem quy trình thao tác và cách xử lý lỗi thường gặp.</li>
                </ul>

                <h3 style='font-size:14px; color:#eac54f; margin:14px 0 8px 0; font-weight:700;'>2) THIẾT LẬP TRƯỚC KHI TẢI</h3>
                <ul style='color:#c9d1d9; line-height:1.7; margin:0 0 8px 18px;'>
                    <li>Vào <b>Cấu hình &amp; Cookie</b>, chọn <b>Định dạng</b>: MP4, MP4 (Convert), MKV, MP3 hoặc FLAC.</li>
                    <li>Bấm <b>Thay đổi...</b> để chọn thư mục lưu. Mặc định là thư mục Downloads của Windows nếu có.</li>
                    <li>Bật <b>Tải xuống phụ đề</b> nếu muốn lưu phụ đề riêng; bật <b>Nhúng phụ đề vào video</b> nếu muốn gắn phụ đề vào file video.</li>
                    <li>Bật <b>Nhúng thumbnail vào file</b> để gắn ảnh bìa, hoặc <b>Cắt quảng cáo với SponsorBlock</b> nếu nguồn hỗ trợ.</li>
                </ul>

                <h3 style='font-size:14px; color:#eac54f; margin:14px 0 8px 0; font-weight:700;'>3) TẢI VIDEO, PLAYLIST HOẶC NHIỀU LINK</h3>
                <ul style='color:#c9d1d9; line-height:1.7; margin:0 0 8px 18px;'>
                    <li>Vào <b>Tiến trình tải</b>, dán một URL hoặc nhiều URL, mỗi link một dòng.</li>
                    <li>Bấm <b>BẮT ĐẦU TẢI</b>. Mỗi link sẽ được thêm vào <b>Hàng đợi tải</b> với mã task riêng.</li>
                    <li>Ứng dụng tải tối đa <b>{MAX_CONCURRENT_DOWNLOADS} task cùng lúc</b>; các link còn lại tự động chờ đến lượt.</li>
                    <li>Với playlist/kênh, app dùng chế độ <b>lazy playlist</b> để vừa đọc danh sách vừa tải, giúp tránh đứng giao diện quá lâu.</li>
                    <li>Thanh tiến độ hiển thị phần trăm, dung lượng và trạng thái: đang chờ, đang tải, hoàn tất, thất bại hoặc đã dừng.</li>
                </ul>

                <h3 style='font-size:14px; color:#eac54f; margin:14px 0 8px 0; font-weight:700;'>4) ĐIỀU KHIỂN HÀNG ĐỢI</h3>
                <ul style='color:#c9d1d9; line-height:1.7; margin:0 0 8px 18px;'>
                    <li><b>Dừng tất cả</b>: hủy các task đang chờ và gửi lệnh dừng đến các task đang tải.</li>
                    <li><b>Xóa danh sách</b>: chỉ xóa các mục đã hoàn tất, thất bại hoặc đã dừng; task đang tải sẽ được giữ lại.</li>
                    <li>Nếu task bị lỗi, xem thông tin ngắn ngay trên item và xem chi tiết trong <b>Nhật ký hệ thống</b>.</li>
                </ul>

                <div style='border:1px solid #2f3f57; border-radius:10px; background:#121c2c; padding:12px 14px; margin:12px 0;'>
                    <div style='color:#58a6ff; font-weight:700; margin-bottom:6px;'>Lưu ý về ffmpeg</div>
                    <div style='color:#c9d1d9; line-height:1.7;'>
                        Các chế độ MP4, MP4 (Convert), MKV, MP3, FLAC, nhúng phụ đề, nhúng thumbnail và SponsorBlock cần ffmpeg.
                        Nếu ứng dụng báo thiếu ffmpeg, hãy cài ffmpeg vào PATH hoặc đặt trong thư mục tools/ffmpeg/bin của app.
                    </div>
                </div>

                <h3 style='font-size:14px; color:#eac54f; margin:14px 0 8px 0; font-weight:700;'>5) ĐĂNG NHẬP COOKIE CHO VIDEO GIỚI HẠN</h3>
                <ul style='color:#c9d1d9; line-height:1.7; margin:0 0 8px 18px;'>
                    <li>Bấm <b>Đăng nhập tài khoản</b> ở thanh bên trái để mở cửa sổ đăng nhập nhúng.</li>
                    <li>Chọn nền tảng: TikTok, YouTube, Facebook, Douyin hoặc Kuaishou, rồi đăng nhập trong trình duyệt nhúng.</li>
                    <li>Sau khi đăng nhập thành công, bấm <b>Tôi đã đăng nhập xong - Lưu cookie</b> hoặc đóng cửa sổ để app lưu cookie tạm.</li>
                    <li>Cookie đang sử dụng sẽ hiện trong tab <b>Cấu hình &amp; Cookie</b>. Cookie tạm được dọn dẹp khi đóng ứng dụng.</li>
                </ul>

                <h3 style='font-size:14px; color:#eac54f; margin:14px 0 8px 0; font-weight:700;'>6) CẬP NHẬT VÀ NHẬT KÝ</h3>
                <ul style='color:#c9d1d9; line-height:1.7; margin:0 0 8px 18px;'>
                    <li>Khi mở app, DLP-Master tự chạy nền lệnh nâng cấp lõi <b>yt-dlp</b>; kết quả sẽ hiện trong log.</li>
                    <li>Nút <b>Kiểm tra cập nhật</b> dùng để kiểm tra phiên bản ứng dụng nếu đã cấu hình UPDATE_URL trong app_config.py.</li>
                    <li>Tab <b>Nhật ký hệ thống</b> hiển thị log tải, lỗi 429, lỗi cookie, ffmpeg, cập nhật yt-dlp và cập nhật ứng dụng.</li>
                    <li>Bấm <b>Xóa log</b> để làm sạch màn hình log, không ảnh hưởng đến task đang tải.</li>
                </ul>

                <h3 style='font-size:14px; color:#eac54f; margin:14px 0 8px 0; font-weight:700;'>7) XỬ LÝ LỖI THƯỜNG GẶP</h3>
                <ul style='color:#c9d1d9; line-height:1.7; margin:0 0 8px 18px;'>
                    <li><b>Thiếu URL</b>: dán link vào ô nhập, mỗi link một dòng nếu tải nhiều video.</li>
                    <li><b>Thiếu ffmpeg</b>: cài ffmpeg hoặc chọn lại cấu hình không cần xử lý media nếu phù hợp.</li>
                    <li><b>HTTP 429 / Too Many Requests</b>: tạm dừng một lúc rồi thử lại; đăng nhập cookie thường giúp ổn định hơn.</li>
                    <li><b>Video giới hạn hoặc yêu cầu đăng nhập</b>: dùng nút <b>Đăng nhập tài khoản</b> để lấy cookie trước khi tải.</li>
                    <li><b>Tên file quá dài/ký tự lạ</b>: app đã giới hạn tiêu đề và bật chế độ tên file thân thiện với Windows.</li>
                </ul>

                <div style='border:1px solid #2f3f57; border-radius:10px; background:#101926; padding:12px 14px; margin:12px 0;'>
                    <div style='color:#58a6ff; font-weight:700; margin-bottom:6px;'>Quy trình khuyến nghị</div>
                    <div style='color:#c9d1d9; line-height:1.7;'>
                        Chọn thư mục lưu -> chọn định dạng -> đăng nhập cookie nếu cần -> dán URL -> BẮT ĐẦU TẢI -> theo dõi hàng đợi và log.
                    </div>
                </div>

                <hr style="border: 0; border-top: 1px solid #30363d; margin-top: 30px; margin-bottom: 15px;"/>
                <div style='font-size:12px; color:#8b949e; line-height:1.7;'>
                    <p><strong>✍️ Tác giả:</strong> TH89</p>
                    <p><strong>📧 Email:</strong> <a href="mailto:Thienhash@gmail.com" style="color: #58a6ff; text-decoration: none;">Thienhash@gmail.com</a></p>
                    <p><strong>🌐 Facebook:</strong> <a href="https://www.facebook.com/nhu.inh.ha" style="color: #58a6ff; text-decoration: none;">nhu.inh.ha</a></p>
                    <p style="margin-top: 15px; font-size: 11px; color: #6e7681;">📦 Mã nguồn mở: <strong>yt-dlp core</strong> | Phiên bản: <span style="color: #238636;">v{VERSION}</span></p>
                </div>
            </div>
            """
        )

        layout.addWidget(self.help_text, 1)
        return page

    def switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for idx, button in enumerate(self.sidebar_buttons):
            button.setChecked(idx == index)

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #0a0f18;
                color: #dbe4ee;
                font-family: "Segoe UI", "Noto Sans", sans-serif;
                font-size: 14px;
            }
            QFrame#Sidebar {
                background: #010409;
                border: 1px solid #1f2937;
                border-radius: 10px;
            }
            QLabel#SidebarTitle {
                color: #58a6ff;
                font-weight: bold;
                font-size: 16px;
                padding-bottom: 10px;
                margin-bottom: 15px;
                border-bottom: 1px solid #30363d;
            }
            QPushButton#SidebarButton {
                text-align: left;
                background: #0f1724;
                color: #9dd2ff;
                border: 1px solid #223249;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QPushButton#SidebarButton:hover {
                background: #132033;
                border-color: #2c4768;
                color: #d7eeff;
            }
            QPushButton#SidebarButton:checked {
                background: #173251;
                border-color: #4b86c2;
                color: #e8f5ff;
            }
            QPushButton#SidebarActionButton {
                text-align: left;
                background: #102132;
                color: #7cc4ff;
                border: 1px solid #315274;
                border-radius: 8px;
                padding: 10px 12px;
                font-weight: 600;
            }
            QPushButton#SidebarActionButton:hover {
                background: #173251;
                border-color: #4b86c2;
                color: #e8f5ff;
            }
            QStackedWidget#ContentStack {
                background: transparent;
            }
            QFrame#ContentCard {
                border-radius: 8px;
                border: 1px solid #30363d;
                background-color: #161b22;
            }
            QFrame#QueueContainer {
                border: 1px solid #253244;
                border-radius: 10px;
                background: #0f1622;
            }
            QLabel#SectionTitle {
                color: #f8fbff;
                font-size: 16px;
                font-weight: 700;
            }
            QLineEdit, QComboBox {
                background: #08101b;
                color: #dbe4ee;
                border: 1px solid #2f3f57;
                border-radius: 8px;
                padding: 11px;
                selection-background-color: #2da6ff;
            }
            QLineEdit#ReadOnlyField {
                background: #0f1724;
                color: #9fb5cd;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #2da6ff;
            }
            QPushButton#StartButton {
                background: #00b86f;
                color: #03150d;
                border: 0;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 800;
                padding: 0 16px;
            }
            QPushButton#StartButton:hover {
                background: #13d181;
            }
            QPushButton#SettingsButton, QPushButton#ClearButton, QPushButton#LoginButton, QPushButton#QueueActionButton, QPushButton {
                background: #101b2a;
                color: #9dd2ff;
                border: 1px solid #355171;
                border-radius: 8px;
                padding: 8px 12px;
            }
            QPushButton#QueueDangerButton {
                background: #2a1313;
                color: #ffb4b4;
                border: 1px solid #8a3b3b;
                border-radius: 8px;
                padding: 8px 12px;
            }
            QScrollArea#QueueScroll {
                border: 0;
                background: transparent;
            }
            QFrame#QueueItem {
                background: #0a1320;
                border: 1px solid #223249;
                border-radius: 10px;
            }
            QLabel#QueueTitle {
                color: #dbe4ee;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#QueueStatus {
                color: #94c8ff;
                font-size: 12px;
                padding: 2px 8px;
                background: #122034;
                border: 1px solid #2d4a6d;
                border-radius: 9px;
            }
            QLabel#QueueStatus[state="done"] {
                color: #96f5c8;
                background: #10271d;
                border: 1px solid #2f8f63;
            }
            QLabel#QueueStatus[state="failed"] {
                color: #ffb9b9;
                background: #2a1111;
                border: 1px solid #9b3f3f;
            }
            QLabel#QueueStatus[state="cancelled"] {
                color: #ffd4a8;
                background: #2a1d10;
                border: 1px solid #91603b;
            }
            QLabel#QueueStatus[state="running"] {
                color: #9dd2ff;
                background: #122034;
                border: 1px solid #2d4a6d;
            }
            QProgressBar {
                border: 1px solid #30435d;
                border-radius: 6px;
                background: #0b1220;
                color: #dbe4ee;
                text-align: center;
                height: 11px;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2da6ff, stop:1 #00d09c);
            }
            QTextEdit#Console {
                background: #00060f;
                color: #8df7b2;
                border: 1px solid #223249;
                border-radius: 10px;
                padding: 10px;
                font-family: Consolas, "Cascadia Mono", monospace;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #ffffff;
                border-radius: 4px;
                background: #161b22;
            }
            QCheckBox::indicator:checked {
                background: #18FFFF;
                border: 2px solid #58a6ff;
            }
            """
        )

    def parse_urls(self, raw: str) -> list[str]:
        normalized = raw.replace(",", "\n")
        parts = [line.strip() for line in normalized.splitlines()]
        return [part for part in parts if part]

    def add_queue_item(self, task: DownloadTask):
        item = QueueItemWidget(task)
        item.mark_queued()
        self.queue_widgets[task.task_id] = item
        self.queue_items_layout.insertWidget(self.queue_items_layout.count() - 1, item)

    def enqueue_from_input(self):
        self.apply_settings_from_controls()
        raw = self.url_input.text().strip()
        if not raw:
            QMessageBox.warning(self, "Thiếu URL", "Hãy dán URL cần tải.")
            return

        urls = self.parse_urls(raw)
        if not urls:
            QMessageBox.warning(self, "URL không hợp lệ", "Không tìm thấy URL trong ô nhập.")
            return

        output_dir = self.download_dir_input.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Thư mục lưu", "Hãy chọn thư mục lưu hợp lệ trước khi tải.")
            return
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except OSError as err:
            QMessageBox.critical(self, "Thư mục lưu", f"Không thể tạo/ghi vào thư mục đã chọn:\n{err}")
            return
        self.settings.output_dir = output_dir

        if not FFMPEG_PATH and self.settings_requires_ffmpeg():
            QMessageBox.critical(
                self,
                "Thiếu ffmpeg",
                "Cài đặt hiện tại cần ffmpeg để convert/xử lý. Hãy cài ffmpeg vào máy tính hoặc đổi cấu hình định dạng khác.",
            )
            return

        for url in urls:
            task = DownloadTask(task_id=uuid.uuid4().hex[:8], url=url)
            self.pending_queue.append(task)
            self.add_queue_item(task)
            self.append_log("info", f"[hàng đợi] Đã thêm {task.task_id}: {url}")

        self.url_input.clear()
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

    def start_task(self, task: DownloadTask):
        item = self.queue_widgets[task.task_id]
        item.mark_running()
        item.meta.setText("Khởi tạo worker...")

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
        self.append_log("warning", f"[hàng đợi] Bắt đầu task {task.task_id}")
        thread.start()

    def handle_task_metadata(self, task_id: str, title: str, size_hint: str):
        item = self.queue_widgets.get(task_id)
        if not item:
            return
        item.set_video_title(title)
        if size_hint and size_hint != "-":
            item.last_size = size_hint
            if item.status.property("state") != "done":
                item.status.setText(f"{size_hint} | Đang tải")

    def handle_task_progress(self, task_id: str, percent: int, size_text: str, details: str):
        item = self.queue_widgets.get(task_id)
        if not item:
            return
        item.update_download_state(percent, size_text, details)

    def handle_task_finished(self, task_id: str, ok: bool, message: str):
        item = self.queue_widgets.get(task_id)
        if item:
            cancelled = "đã dừng bởi người dùng" in clean_log_text(message).lower()
            if ok:
                item.mark_done()
                item.meta.setText(f"{item.last_size} | Hoàn tất")
            elif cancelled:
                item.mark_cancelled()
                item.meta.setText("Đã dừng bởi người dùng")
            else:
                item.mark_failed()
                item.meta.setText(clean_log_text(message))

        level = "success" if ok else "error"
        prefix = "[done]" if ok else "[failed]"
        self.append_log(level, f"{prefix} {task_id}: {clean_log_text(message)}")

    def handle_thread_finished(self, task_id: str):
        timer = self.force_stop_timers.pop(task_id, None)
        if timer:
            timer.stop()
            timer.deleteLater()
        self.active_threads.pop(task_id, None)
        self.pump_queue()

    def update_cookie_status(self):
        if self.settings.cookie_file and Path(self.settings.cookie_file).exists():
            self.cookie_status.setText(f"Cookie đang sử dụng: {self.settings.cookie_file}")
        else:
            self.cookie_status.setText("Cookie mode: Public/Ẩn danh (chưa đăng nhập)")

    def set_update_channel(self, channel: str):
        self.update_channel = (channel or "stable").strip().lower()
        self.append_log("info", f"[update] Update channel: {self.update_channel}")

    def check_for_updates_silent(self):
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual: bool = False):
        if not self.update_url:
            self.append_log("warning", "[update] Chưa cấu hình UPDATE_URL trong app_config.py")
            return
        if self.update_check_thread and self.update_check_thread.isRunning():
            return

        if manual:
            self.append_log("info", "[update] Đang kiểm tra cập nhật...")
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
            self.append_log("warning", f"[update] Không thể kiểm tra cập nhật: {clean_log_text(message)}")
            if manual and hasattr(self, "release_notes_view"):
                self.release_notes_view.setPlainText(f"Update error: {clean_log_text(message)}")
            return

        self.pending_update_result = result
        manifest = result.manifest
        self.latest_release_url = manifest.download_url
        if hasattr(self, "latest_version_label"):
            self.latest_version_label.setText(f"Latest Version: v{result.latest_version}")
        if hasattr(self, "release_notes_view"):
            self.release_notes_view.setPlainText(manifest.release_notes or "Release Notes: -")

        if not result.is_supported:
            self.append_log("warning", f"[update] Phiên bản hiện tại thấp hơn minimum_version v{manifest.minimum_version}.")

        if result.update_available:
            self.append_log("warning", f"[update] Có phiên bản mới v{result.latest_version} (hiện tại v{result.current_version}).")
            if result.latest_version == self.skipped_update_version:
                return
            if manual or self.update_prompted_version != result.latest_version:
                self.update_prompted_version = result.latest_version
                self.show_update_dialog(result)
        elif manual:
            self.append_log("success", f"[update] Đang ở phiên bản mới nhất: v{self.current_version}")

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
        self.append_log("info", f"[update] Đã bỏ qua phiên bản v{version}")
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

        self.update_download_thread = UpdateDownloadThread(manifest, str(target_dir), CONFIG_APP_NAME)
        self.update_download_thread.download_progress.connect(self.on_update_download_progress)
        self.update_download_thread.download_finished.connect(self.on_update_download_finished)
        self.update_download_thread.finished.connect(self.update_download_thread.deleteLater)
        self.update_download_thread.finished.connect(self._clear_update_download_thread)
        self.update_download_thread.start()

    def on_update_download_progress(self, percent: int, status: str):
        if self.update_dialog:
            self.update_dialog.set_progress(percent, status)

    def on_update_download_finished(self, success: bool, package_path: str, message: str):
        if success:
            self.downloaded_update_package = package_path
            self.append_log("success", f"[update] Đã tải và xác minh SHA256: {package_path}")
            if self.update_dialog:
                self.update_dialog.set_progress(100, "Đã tải xong và xác minh SHA256. Sẵn sàng cài đặt.")
                self.update_dialog.set_ready_to_install(True)
        else:
            self.append_log("warning", f"[update] Tải cập nhật thất bại: {clean_log_text(message)}")
            if self.update_dialog:
                self.update_dialog.set_progress(0, f"Tải cập nhật thất bại: {clean_log_text(message)}")
                self.update_dialog.set_download_running(False)

    def _clear_update_download_thread(self):
        self.update_download_thread = None

    def cancel_update_download(self):
        if self.update_download_thread and self.update_download_thread.isRunning():
            self.update_download_thread.cancel()
            self.append_log("warning", "[update] Đang hủy tải cập nhật...")

    def install_downloaded_update(self):
        if not self.downloaded_update_package:
            self.append_log("warning", "[update] Chưa có gói cập nhật đã tải.")
            return
        if self.active_threads:
            self.append_log("warning", "[update] Hãy dừng hoặc đợi các task tải hoàn tất trước khi cài cập nhật.")
            return
        try:
            launch_updater(self.downloaded_update_package, app_root(), restart=True)
        except Exception as err:
            self.append_log("error", f"[update] Không thể mở updater: {clean_log_text(err)}")
            return

        self.append_log("success", "[update] Đã mở DLP Master Updater. Ứng dụng chính sẽ đóng để cài cập nhật.")
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
            QMessageBox.critical(self, "Lỗi đăng nhập", f"Không thể mở cửa sổ đăng nhập:\n{err}")
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
        current_dir = self.download_dir_input.text().strip() or self.get_default_download_dir()
        selected_dir = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu video/audio", current_dir)
        if selected_dir:
            self.download_dir_input.setText(selected_dir)
            self.settings.output_dir = selected_dir
            self.append_log("info", f"[cài đặt] Thư mục lưu mới: {selected_dir}")

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
        self.append_log("info", "[hệ thống] Log đã được xóa")

    def clear_completed_items(self):
        removed = 0
        for task_id, item in list(self.queue_widgets.items()):
            if task_id in self.active_threads:
                continue
            state = item.status.property("state")
            if state not in {"done", "failed", "cancelled"}:
                continue
            self.queue_items_layout.removeWidget(item)
            item.deleteLater()
            del self.queue_widgets[task_id]
            removed += 1
        if removed:
            self.append_log("info", f"[hàng đợi] Đã xóa {removed} item")

    def stop_all_tasks(self):
        self.pending_queue.clear()
        for task_id, item in self.queue_widgets.items():
            if task_id not in self.active_threads and item.status.property("state") == "queued":
                item.mark_cancelled()

        for task_id, (thread, worker) in list(self.active_threads.items()):
            worker.stop()
            if task_id not in self.force_stop_timers:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda task_id=task_id: self.force_terminate_task(task_id))
                timer.start(3000)
                self.force_stop_timers[task_id] = timer

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
            QMessageBox.information(self, "Đang tải", "Hãy đợi hoàn tất hoặc dừng các task trước khi đóng ứng dụng.")
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
        QMessageBox.information(None, "Da mo san", "DLP Master dang chay o cua so khac.")
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
