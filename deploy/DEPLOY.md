# 🚀 Deploy lên VPS (Ubuntu/Debian)

Hướng dẫn deploy **World Cup 2026 Predictor** lên server công khai bằng Docker.
Sau khi deploy: UI chạy ở **http://SERVER_IP/** (port 80), backend chỉ chạy nội bộ
trong Docker network (không expose port 8000 — các endpoint ghi như `/api/refresh`,
`/api/ml/retrain` chưa có auth nên không được mở ra ngoài).

---

## ⚠️ Bảo mật — làm NGAY trước lần deploy đầu

Mật khẩu root đã từng được gửi qua chat/chat log → coi như đã lộ:

```bash
ssh root@SERVER_IP
passwd                                   # 1. đổi mật khẩu root ngay

# 2. tạo SSH key trên máy local (nếu chưa có) rồi cài lên server
#    (chạy ở máy LOCAL)
ssh-keygen -t ed25519                    # enter qua các bước
ssh-copy-id root@SERVER_IP

# 3. tắt đăng nhập bằng mật khẩu (trên SERVER, sau khi key đã vào được)
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# 4. firewall: chỉ mở SSH + HTTP
apt-get update && apt-get install -y ufw
ufw allow 22/tcp && ufw allow 80/tcp && ufw --force enable
```

---

## Cách 1 — Deploy tự động từ máy dev (khuyên dùng)

Từ thư mục gốc repo trên máy local (cần `rsync` + SSH vào được server):

```bash
bash deploy/push.sh root@SERVER_IP
```

Script sẽ:
1. `rsync` toàn bộ code (kèm `.env` và ML artifacts đã train) → `/opt/wc2026`
   (loại trừ: `.git`, `node_modules`, `.venv`, cache SQLite, dataset ML)
2. Chạy `deploy/deploy.sh` trên server: tự cài Docker nếu thiếu → build → start
   với port production → đợi healthcheck → in trạng thái.

Deploy lại sau khi sửa code: chạy lại đúng lệnh đó (rsync chỉ đẩy phần thay đổi).

## Cách 2 — Clone từ GitHub trên server (1 script)

```bash
# B1 (máy LOCAL): copy .env lên server — file này gitignore, KHÔNG có trên GitHub
scp .env root@SERVER_IP:/opt/wc2026/.env     # tạo thư mục trước nếu cần: ssh root@SERVER_IP mkdir -p /opt/wc2026

# B2 (trên SERVER): clone + chạy 1 script là xong
git clone https://github.com/ttkien2035/AI-WC-Football.git /opt/wc2026
cd /opt/wc2026 && bash deploy/deploy.sh

# Cập nhật khi có commit mới:
bash deploy/deploy.sh --update      # git pull + rebuild + restart
```

---

## Kiến trúc trên server

```
Internet ──:80──> [frontend: nginx]──/api──> [backend: FastAPI] (nội bộ)
                       │ static React           │ scheduler + auto-retrain 03:00 UTC
                       └ SPA                    ├ volume cache_data  (SQLite: match log, góc)
                                                └ volume models_data (ML artifacts, retrain đêm)
```

- **Scheduler chạy trong container**: tự refresh theo lịch thi đấu (60s khi live),
  ghi timeline xác suất, retrain ML hàng đêm — không cần cron ngoài.
- **Volumes** giữ data qua restart/rebuild; xoá sạch: `docker compose down -v`.

## Vận hành

```bash
cd /opt/wc2026
docker compose ps                                    # trạng thái
docker compose logs -f backend                       # log scheduler/ML
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build   # rebuild
docker compose restart backend                       # restart nhanh
curl -s localhost/api/sources/status | python3 -m json.tool   # health các nguồn data
```

## (Tuỳ chọn) HTTPS với domain

Trỏ domain A-record → SERVER_IP, rồi dùng Caddy làm reverse proxy tự động SSL:

```bash
# đổi port frontend trong deploy/docker-compose.prod.yml thành "127.0.0.1:8080:80"
apt-get install -y caddy
cat > /etc/caddy/Caddyfile << 'EOF'
yourdomain.com {
    reverse_proxy 127.0.0.1:8080
}
EOF
systemctl restart caddy
ufw allow 443/tcp
```

## Khắc phục sự cố

| Triệu chứng | Kiểm tra |
|---|---|
| UI trắng / 502 | `docker compose ps` — backend healthy chưa? `docker compose logs backend` |
| Không có dữ liệu trận | `.env` có `FOOTBALL_API_KEY` đúng? `curl -s localhost/api/sources/status` |
| Build chậm/treo | VPS RAM < 2GB có thể thiếu khi build — thêm swap: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
| Retrain đêm fail | `docker compose logs backend \| grep retrain` — artifacts cũ vẫn được giữ, app không hỏng |
