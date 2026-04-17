# BTC_24-7bot

Bot GitHub Actions tự động lấy **giá BTC trên sàn OKX** và gửi về **Telegram** mỗi giờ.

---

## ⚡ Tính năng

- Lấy giá BTC/USDT từ **OKX Public API**.
- Gửi giá trực tiếp về **Telegram**.
- Chạy **1 tiếng/lần** hoặc trigger thủ công.
- Có log debug để kiểm tra workflow và tin nhắn Telegram.

---

## 🛠️ Cài đặt

1. **Tạo repository mới trên GitHub**.
2. **Commit file README.md đầu tiên** → branch `main` xuất hiện.
3. **Thêm Secrets** trong repo:
   - `BOT_TOKEN`: Token bot Telegram từ BotFather.
   - `CHAT_ID`: Chat ID cá nhân hoặc nhóm Telegram nhận tin nhắn.

---

## ⚙️ Workflow

- Tạo folder `.github/workflows/`.
- Tạo file workflow, ví dụ: `btc_okx_telegram.yml`.
- Nội dung workflow sẽ:
  1. Setup Python.
  2. Cài `requests`.
  3. Lấy giá BTC từ OKX API.
  4. Gửi giá về Telegram.

> Cron schedule mặc định: `'0 * * * *'` → 1 giờ/lần.

---

## 📝 Sử dụng

1. Push workflow lên repo.
2. Vào tab **Actions** để kiểm tra workflow chạy.
3. Telegram sẽ nhận tin nhắn với giá BTC mới nhất.
4. Có thể trigger workflow thủ công bằng **Run workflow**.

---

## 💡 Ghi chú

- Nếu bot không gửi tin nhắn: kiểm tra lại **BOT_TOKEN**, **CHAT_ID**, hoặc log debug trong Actions.
- Có thể chỉnh cron để chạy theo tần suất mong muốn.
- Có thể mở rộng workflow để gửi tin nhắn nhiều chat cùng lúc hoặc alert biến động lớn của BTC.
