# Deploy — Phương án B (VM always-on, team truy cập)

Dashboard chạy trong container `uvicorn`, sau Caddy lo **HTTPS + basic auth** (vì app
không có auth riêng). State (artifacts, prompt/model overrides) nằm trên volume `./data`
nên sống qua restart. **1 instance** — đừng scale ra nhiều bản (run-state nằm trong RAM,
mỗi process chỉ chạy 1 run/lúc).

## File deploy
| File | Vai trò |
|---|---|
| `Dockerfile` | image Python 3.11-slim chạy `python -m embroidery.web --no-browser` |
| `.dockerignore` | loại venv/data/tests khỏi image |
| `requirements.txt` | deps pin từ venv thật |
| `docker-compose.yml` | 2 service: `app` (không expose ra host) + `caddy` (80/443) |
| `Caddyfile` | reverse proxy → `app:8765`, basic auth, `flush_interval -1` cho SSE |
| `.env` | API keys + `SITE_ADDRESS`/`BASIC_AUTH_*` (gitignored) |

## Các bước trên VM

1. **Chuẩn bị VM** (GCP e2-micro free-tier / AWS t4g.nano / Hetzner / DO $4–6).
   Cài Docker + compose plugin. Mở firewall port **80, 443**.

2. **Lấy code & cấu hình**
   ```bash
   git clone <repo> && cd agent-teams/embroidery
   cp .env.example .env          # điền GEMINI_API_KEY, BRAVE_API_KEY
   ```

3. **Tạo basic-auth hash** rồi điền vào `.env`
   ```bash
   docker run --rm caddy:2-alpine caddy hash-password -p 'MAT_KHAU_CUA_BAN'
   # dán kết quả vào BASIC_AUTH_HASH=, đặt BASIC_AUTH_USER=, SITE_ADDRESS=dashboard.domain.com
   ```
   Trỏ DNS A record của domain về IP VM trước khi Caddy xin cert.

4. **Chạy**
   ```bash
   docker compose up -d --build
   docker compose logs -f app          # xem khởi động
   ```

5. **Smoke test** (xác nhận loop + tools + ghi file với key thật)
   ```bash
   docker compose exec app python -m tests.smoke_test
   ```

6. **Truy cập** `https://dashboard.domain.com` → nhập user/pass basic auth.

## Vận hành
- **Cập nhật code:** `git pull && docker compose up -d --build`.
- **Backup:** chỉ cần backup thư mục `./data` (artifacts + `prompts/*overrides.json` + `brand_ai/`).
- **Tự sống lại:** `restart: unless-stopped` lo reboot/crash.

## Tối ưu chi phí
- Hosting ≈ $0–6/tháng; **chi phí thật là token LLM** mỗi run.
- Giữ Gemini flash cho search/JSON, pro cho reasoning (mặc định trong `config.yaml`).
- Siết `search.max_searches` / `max_searches_per_agent`; cân nhắc `search.provider: duckduckgo` (free) để bỏ phí Brave.
- Theo dõi `$/run` ở `data/output/run_report.md`; đặt budget alert ở Google AI Studio/Cloud.
- Dùng thưa → cân nhắc tắt VM khi không dùng (nhưng B đã thiết kế để always-on cho team).

## Cảnh báo bảo mật
- **Không** publish port 8765 ra host — chỉ Caddy được expose. App không tự auth.
- `.env` chứa API key — không commit (đã gitignore). Trên VM nên đặt quyền `chmod 600 .env`.
