import asyncio
import base64
import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

from yt_dlp import YoutubeDL
from yt_dlp.version import __version__


BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
DOWNLOAD_DIR = BASE_DIR / "downloads"
SECRET_KEY = "SUPER_SECRET_KEY_FOR_YT_DLP"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"
TOKEN_TTL_SECONDS = 12 * 60 * 60

app = FastAPI(title="yt-dlp WebUI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginModel(BaseModel):
    username: str
    password: str


class DownloadRequest(BaseModel):
    url: HttpUrl
    preset: Literal["best", "mp4", "mp3"] = "best"
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    write_subs: bool = False
    sponsorblock: bool = False
    cookies_from_browser: bool = False


class LogHub:
    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self._clients.discard(websocket)

    async def broadcast(self, level: str, message: str):
        stale_clients = []
        payload = {"type": level, "message": message}
        for websocket in list(self._clients):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                stale_clients.append(websocket)
        for websocket in stale_clients:
            self.disconnect(websocket)

    def publish(self, level: str, message: str):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.broadcast(level, message))
            )


hub = LogHub()


@app.on_event("startup")
async def on_startup():
    hub.set_loop(asyncio.get_running_loop())
    DOWNLOAD_DIR.mkdir(exist_ok=True)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "role": "admin",
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64url(signature)}"


def verify_access_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    body, signature = token.rsplit(".", 1)
    expected = _b64url(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError):
        return False
    return payload.get("role") == "admin" and int(payload.get("exp", 0)) > time.time()


class WebUILogger:
    def debug(self, message):
        if message.startswith("[debug]"):
            return
        hub.publish("info", message)

    def warning(self, message):
        hub.publish("warning", message)

    def error(self, message):
        hub.publish("error", message)


def progress_hook(status):
    state = status.get("status")
    if state == "downloading":
        percent = status.get("_percent_str", "").strip()
        speed = status.get("_speed_str", "").strip()
        eta = status.get("_eta_str", "").strip()
        hub.publish("download", f"[download] {percent} at {speed}, ETA {eta}")
    elif state == "finished":
        filename = Path(status.get("filename", "")).name
        hub.publish("success", f"[download] Finished: {filename}")


def postprocessor_hook(status):
    name = status.get("postprocessor") or "postprocessor"
    if status.get("status") == "started":
        hub.publish("info", f"[{name}] Started")
    elif status.get("status") == "finished":
        hub.publish("success", f"[{name}] Finished")


def build_ydl_options(request: DownloadRequest) -> dict:
    output_template = str(DOWNLOAD_DIR / "%(title).200B [%(id)s].%(ext)s")
    options = {
        "outtmpl": {"default": output_template},
        "logger": WebUILogger(),
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "noplaylist": False,
        "windowsfilenames": True,
        "ignoreerrors": False,
        "retries": 10,
        "fragment_retries": 10,
    }

    if request.preset == "mp3":
        options.update({
            "format": "ba/b",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }],
        })
    elif request.preset == "mp4":
        options.update({
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "merge_output_format": "mp4",
        })
    else:
        options.update({"format": "bv*+ba/b"})

    if request.write_subs:
        options.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["all"],
        })

    postprocessors = options.setdefault("postprocessors", [])
    if request.embed_metadata:
        postprocessors.append({
            "key": "FFmpegMetadata",
            "add_chapters": True,
            "add_metadata": True,
            "add_infojson": False,
        })
    if request.embed_thumbnail:
        options["writethumbnail"] = True
        postprocessors.append({"key": "EmbedThumbnail"})
    if request.sponsorblock:
        postprocessors.append({"key": "SponsorBlock", "categories": ["sponsor"], "when": "after_filter"})
        postprocessors.append({
            "key": "ModifyChapters",
            "remove_chapters_patterns": [],
            "remove_sponsor_segments": [],
            "remove_ranges": [],
            "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l",
            "force_keyframes": False,
        })
    if request.cookies_from_browser:
        options["cookiesfrombrowser"] = ("chrome",)

    return options


def run_download(request: DownloadRequest):
    hub.publish("info", f"[yt-dlp] Starting {request.preset} download: {request.url}")
    with YoutubeDL(build_ydl_options(request)) as ydl:
        ydl.download([str(request.url)])
    hub.publish("success", "[yt-dlp] Download complete")


@app.get("/")
async def index():
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(INDEX_FILE)


@app.get("/api/status")
async def api_status():
    usage = shutil.disk_usage(DOWNLOAD_DIR)
    return {
        "version": __version__,
        "download_dir": str(DOWNLOAD_DIR),
        "free_gb": round(usage.free / (1024 ** 3), 2),
    }


@app.post("/api/login")
async def login(data: LoginModel):
    if data.username == ADMIN_USERNAME and data.password == ADMIN_PASSWORD:
        return {"access_token": create_access_token(data.username), "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Tai khoan hoac mat khau khong chinh xac")


@app.post("/api/download")
async def api_download(request: DownloadRequest):
    asyncio.create_task(asyncio.to_thread(run_download, request))
    return {"ok": True, "message": "Download queued"}


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        token_data = await websocket.receive_json()
        if not verify_access_token(token_data.get("token")):
            await websocket.send_json({"type": "error", "message": "Xac thuc that bai"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await hub.connect(websocket)
        await websocket.send_json({
            "type": "success",
            "message": f"Connected to yt-dlp core v{__version__}",
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
