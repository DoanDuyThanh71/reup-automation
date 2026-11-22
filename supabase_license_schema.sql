-- Chạy đoạn SQL này trong Supabase SQL Editor (hoặc PostgreSQL) để lưu tự động
-- Tài khoản khách hàng + Vân tay máy (HWID) khi họ mở ReupAutomationStudio.exe lần đầu!

CREATE TABLE IF NOT EXISTS public.client_devices (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT,
    hwid TEXT NOT NULL UNIQUE,
    license_key TEXT,
    plan TEXT DEFAULT 'FREE_TRIAL',
    is_blocked BOOLEAN DEFAULT FALSE,
    os TEXT,
    gpu_name TEXT,
    vram_gb NUMERIC,
    ram_gb NUMERIC,
    cpu_threads INTEGER,
    app_version TEXT,
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.client_devices ENABLE ROW LEVEL SECURITY;

-- Cho phép bản .exe đăng ký lần đầu (INSERT) vào bảng client_devices bằng anon key:
CREATE POLICY "Allow first launch device registration"
ON public.client_devices
FOR INSERT
TO anon
WITH CHECK (true);
