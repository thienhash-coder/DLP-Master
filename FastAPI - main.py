import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta

app = FastAPI()

# Cấu hình CORS để Frontend có thể gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "SUPER_SECRET_KEY_FOR_YT_DLP"
ALGORITHM = "HS256"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123" # Thay bằng mật khẩu bảo mật hơn khi chạy thật

class LoginModel(BaseModel):
    username: str
    password: str

# Hàm tạo Token JWT
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=12)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# API Đăng nhập
@app.post("/api/login")
def login(data: LoginModel):
    if data.username == ADMIN_USERNAME and data.password == ADMIN_PASSWORD:
        token = create_access_token({"sub": data.username, "role": "admin"})
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Tài khoản hoặc mật khẩu không chính xác")

# WebSocket Stream Log bảo mật dành riêng cho Admin
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        # Nhận tin nhắn đầu tiên chứa Token để xác thực
        token_data = await websocket.receive_json()
        token = token_data.get("token")
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("role") != "admin":
                raise Exception("Không phải Admin")
        except Exception:
            await websocket.send_json({"type": "error", "message": "Xác thực thất bại! Từ chối kết nối."})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.send_json({"type": "info", "message": " Đã kết nối an toàn với máy chủ yt-dlp core."})
        
        # Giả lập stream log liên tục từ yt-dlp sang cho Admin
        logs_sample = [
            {"type": "info", "message": "Kiểm tra hệ thống: core yt_dlp ready (v2026.x)"},
            {"type": "info", "message": "Đã tải 1,731 extractors từ file supportedsites.md"},
            {"type": "warning", "message": "[youtube] Khởi chạy trích xuất dữ liệu bằng trình duyệt giả lập..."},
            {"type": "success", "message": "[youtube] Đã bypass thành công hàng rào xác thực Geo-restriction"},
            {"type": "download", "message": "[download] Đang tải: 12.4% of 45.20MiB at 8.42MiB/s"},
            {"type": "download", "message": "[download] Đang tải: 45.8% of 45.20MiB at 9.11MiB/s"},
            {"type": "success", "message": "[ffmpeg] Đang nhúng phụ đề và merge luồng Video + Audio..."},
            {"type": "info", "message": "[SponsorBlock] Đã tìm thấy và cắt bỏ 2 phân đoạn quảng cáo."},
            {"type": "success", "message": "[postprocessor] Hoàn thành! File đã được di chuyển vào thư mục lưu trữ."}
        ]
        
        for log in logs_sample:
            await asyncio.sleep(2)  # Giả lập độ trễ thời gian thực
            await websocket.send_json(log)
            
        while True:
            # Giữ kết nối luôn mở
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print("Admin disconnected")