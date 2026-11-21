# 🤖 AI Agent Installation & Operations Playbook (`AGENTS.md` / `CLAUDE.md`)

Nếu bạn là một **AI Coding Agent** (Claude Code, Antigravity, Cursor, OpenClaw, Devin, Codex...) được người dùng giao nhiệm vụ cài đặt, cấu hình, kiểm thử hoặc chạy repo **`reup-automation`** này trên **VPS (Linux)** hoặc **Local (Windows / macOS / Linux)**, hãy làm theo đúng hướng dẫn chuẩn dưới đây.

---

## 1. Quy trình Cài đặt Tự động Không Lỗi (Zero-Failure Setup)

### Trường hợp A: Trên Linux VPS hoặc macOS (Có hoặc Không có Docker)
Chỉ cần chạy **1 lệnh duy nhất**:
```bash
bash install.sh
```
**Cơ chế tự bảo vệ đã được tích hợp sẵn trong `install.sh`:**
- **Tự động sửa lỗi CRLF**: Nếu repo được clone từ Windows bị dính `\r`, `install.sh` tự động strip `\r` trước khi chạy.
- **Tự động nhận diện `root` vs `sudo`**: Hoạt động trơn tru trên cả VPS tối giản (LXC/Proxmox chạy `root` không có lệnh `sudo`) lẫn user thường.
- **Tự động xử lý trùng Port (Port Conflict)**: Nếu port `8000` đang bị chiếm bởi ứng dụng khác, script tự động dò port trống tiếp theo (`8001`, `8002`...), cập nhật vào `.env` và in ra URL chính xác.
- **Tự động Fallback Docker $\rightarrow$ Native Python**: Nếu VPS có Docker Compose, script sẽ chạy container; nếu Docker daemon bị lỗi hoặc VPS LXC không hỗ trợ Docker, script **tự động chuyển sang cài đặt Native Python (`.venv`) + FFmpeg** mà không báo lỗi dừng giữa chừng.
- **Tự động đóng gói FFmpeg (`imageio-ffmpeg`)**: Ngay cả khi `apt` / `yum` / `apk` của hệ điều hành không cài được gói `ffmpeg`, Python sẽ tự động tải binary `ffmpeg` tĩnh qua gói `imageio-ffmpeg`.

### Trường hợp B: Trên Windows (Local PC hoặc Windows Server VPS)
Chạy lệnh PowerShell sau:
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```
Sau đó khởi chạy server:
```powershell
.\.venv\Scripts\python.exe run.py
```
*(Hoặc nhấn đúp vào file `start.bat`).*

---

## 2. Kiểm tra Sức khỏe Hệ thống & Tự Chẩn đoán (Self-Verification)

Sau khi cài đặt, Agent hãy chạy các lệnh sau để xác nhận hệ thống đạt 100%:

1. **Chạy trình chẩn đoán hệ thống (`doctor.py`)**:
   ```bash
   python doctor.py
   # Hoặc nếu dùng venv:
   .venv/bin/python doctor.py
   ```
   *Kết quả kỳ vọng*: Exit code `0`, xác nhận Python $\ge 3.10$, các thư mục `data/`, `outputs/`, `temp/` có quyền ghi, FFmpeg binary hoạt động, và SQLite DB đã khởi tạo đủ cấu hình mặc định.

2. **Chạy bộ kiểm thử tự động (`pytest`)**:
   ```bash
   pytest -v
   ```
   *Kết quả kỳ vọng*: `100% passed` (toàn bộ bài test đều mock offline, không cần internet hay API key thật).

3. **Kiểm tra HTTP Healthcheck của Server đang chạy**:
   ```bash
   curl -s http://localhost:8000/api/health
   ```
   *Kết quả kỳ vọng*: `{"status":"ok","database":true,"ffmpeg_binary":"...","version":"1.0.0"}`

---

## 3. Cấu hình Token qua REST API (Dành cho Agent muốn nạp sẵn Token giúp User)

Nếu người dùng cung cấp sẵn các Token trong khung chat (ví dụ Facebook Page ID, Page Access Token, 9Router/OpenAI API Key, Vbee Cookie, Shopee Sub-ID), Agent có thể nạp thẳng vào hệ thống qua API mà không cần mở trình duyệt:

```bash
curl -X POST http://localhost:8000/api/configs \
  -H "Content-Type: application/json" \
  -d '{
    "configs": {
      "FACEBOOK_PAGE_ID": "YOUR_PAGE_ID",
      "FACEBOOK_PAGE_ACCESS_TOKEN": "YOUR_PAGE_TOKEN",
      "FACEBOOK_PUBLISH_MODE": "reel",
      "FACEBOOK_AUTO_PUBLISH": "true",
      "AI_BASE_URL": "https://9router.n8n71.com/v1",
      "AI_API_KEY": "YOUR_AI_KEY",
      "AI_MODEL": "AiFF"
    }
  }'
```
Và kiểm tra kết nối ngay bằng API:
```bash
curl -X POST http://localhost:8000/api/test-connection \
  -H "Content-Type: application/json" \
  -d '{"target": "facebook"}'
```

---

## 4. Xử lý Sự cố Thường gặp trên VPS (Troubleshooting Checklist cho Agent)

- **Không truy cập được `http://<IP_VPS>:8000` từ bên ngoài**:
  - Kiểm tra firewall trên VPS: `ufw allow 8000/tcp` hoặc mở port `8000` trong Security Group của nhà cung cấp VPS (AWS, GCP, Vietnix, Vultr, DigitalOcean...).
- **Muốn ép chạy Native Python thay vì Docker trên VPS RAM thấp (< 1GB)**:
  - Chạy: `FORCE_NATIVE=1 bash install.sh`
