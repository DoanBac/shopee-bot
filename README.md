# Shopee Salework Bot

Bot tự động hỗ trợ trả lời tin nhắn khách Shopee trong Salework Chat.

Hiện repo có 2 hướng chạy:

- `RUN_SALEWORK_BOT.ps1`: bot UI đang dùng thực tế, điều khiển Salework Chat bằng OpenClaw + Edge.
- FastAPI webhook: phần thử nghiệm cũ, chỉ dùng khi Salework có webhook tin nhắn/reply API đầy đủ.

## Chạy bot Salework Chat

Trên máy mới cần có:

- Windows + Microsoft Edge.
- Python 3.11+.
- Node.js/npm nếu máy chưa cài OpenClaw.
- File `.env` có `GEMINI_API_KEY`.
- Đã đăng nhập Salework trong Edge.

Chạy một lệnh:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1
```

Nếu bot đang chạy và muốn restart:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1 -Restart
```

Script sẽ tự:

- Tạo `venv` nếu thiếu.
- Cài `requirements.txt`.
- Kiểm tra/cài OpenClaw nếu có npm.
- Mở Salework Chat bằng profile Edge chính.
- Mở một Edge riêng để tra cứu Shopee.
- Start bot và ghi log vào `openclaw-logs/`.

Dừng bot:

```powershell
.\scripts\stop_salework_gemini_bot.ps1
```

Xem log:

```powershell
Get-Content .\openclaw-logs\salework_gemini_bot.stdout.log -Tail 120 -Encoding UTF8
Get-Content .\openclaw-logs\salework_gemini_bot.stderr.log -Tail 80 -Encoding UTF8
```

## Phạm vi auto-reply hiện tại

Bot chỉ được tự trả lời các case an toàn:

- Khách xin video/hướng dẫn lắp sản phẩm, nhưng chỉ gửi link video trực tiếp đúng mã sản phẩm.
- Khách hỏi kích thước/thông tin có trong mô tả sản phẩm.
- Một số câu thông tin sản phẩm đơn giản đã có rule chắc chắn.

Bot không được trả lời và phải để người xử lý:

- Hoàn hàng, hoàn tiền, đổi trả.
- Thiếu ốc, thiếu phụ kiện, thiếu tấm/ngăn/chi tiết.
- Hàng lỗi, vỡ, sứt, sai màu, khách đang cáu/thất vọng.
- Chi phí, phí hư, bồi thường, số tài khoản, Zalo/số điện thoại.
- Tin có hình ảnh/video/file khách gửi.

## Env cần điền

Tạo `.env` từ `.env.example`, tối thiểu cần:

```text
GEMINI_API_KEY=
```

Các biến Salework/Zalo API chỉ cần nếu chạy hướng webhook/API:

```text
SALEWORK_TOKEN=
SALEWORK_REPLY_URL=
SALEWORK_REPLY_MODE=api
ZALO_TOKEN=
ZALO_MESSAGE_URL=
ZALO_RECIPIENT_ID=
```

Không commit `.env` lên Git.

## Prompt cho AI trên máy khác

Dùng file `PROMPT_CHO_AI_MAY_KHAC.md` để đưa cho AI/Codex trên máy khác. File đó nói rõ bot làm gì, cần kiểm tra gì, chạy script nào, và những rule không được vi phạm.

## FastAPI webhook cũ

Chạy local:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Webhook local:

```text
POST http://127.0.0.1:8000/webhook/salework
```

Vì schema Salework chưa được xác nhận, bot đang parse nhiều field phổ biến như `conversation_id`, `customer_id`, `message.text`, `data.message.content`, `attachments[].url`.
Khi có tài liệu chính thức từ Salework, cần đối chiếu lại payload và endpoint gửi reply.

Nếu Salework/workflow chỉ cho gọi webhook và lấy response để gửi tiếp, dùng chế độ webhook response:

```text
SALEWORK_REPLY_MODE=webhook_response
SALEWORK_WEBHOOK_REPLY_FIELD=reply
```

Khi đó `POST /webhook/salework` sẽ trả JSON có các field `reply`, `message`, `text` để workflow map sang bước gửi tin nhắn.
