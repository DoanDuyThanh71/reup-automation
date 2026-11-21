import os
import socket
import uvicorn
from dotenv import load_dotenv

load_dotenv()

def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        check_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        return s.connect_ex((check_host, port)) == 0

def find_available_port(host: str, preferred_port: int, max_tries: int = 20) -> int:
    port = preferred_port
    for _ in range(max_tries):
        if not is_port_in_use(host, port):
            return port
        port += 1
    return preferred_port

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    preferred_port = int(os.getenv("PORT", "8000"))
    strict_port = os.getenv("STRICT_PORT", "false").lower() in ("true", "1", "yes")

    port = preferred_port if strict_port else find_available_port(host, preferred_port)
    if port != preferred_port:
        print(f"⚠️ Port {preferred_port} đang bận, tự động chuyển sang Port {port}")

    reload_flag = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")
    print(f"🚀 Starting Reup Automation Server at http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_flag)
