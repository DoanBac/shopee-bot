# Shopee Salework Bot

FastAPI webhook nhận tin từ Salework, gọi Gemini để trả lời, báo case cần người xử lý qua Zalo và gửi report cuối ngày.

## Chạy local

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Webhook local:

```text
POST http://127.0.0.1:8000/webhook/salework
```

## Env cần điền

Sao chép hoặc sửa `.env`:

```text
GEMINI_API_KEY=
SALEWORK_TOKEN=
SALEWORK_REPLY_URL=
SALEWORK_REPLY_MODE=api
ZALO_TOKEN=
ZALO_MESSAGE_URL=
ZALO_RECIPIENT_ID=
```

Vì schema Salework chưa được xác nhận, bot đang parse nhiều field phổ biến như `conversation_id`, `customer_id`, `message.text`, `data.message.content`, `attachments[].url`.
Khi có tài liệu chính thức từ Salework, cần đối chiếu lại payload và endpoint gửi reply.

Nếu Salework/workflow chỉ cho gọi webhook và lấy response để gửi tiếp, dùng chế độ webhook response:

```text
SALEWORK_REPLY_MODE=webhook_response
SALEWORK_WEBHOOK_REPLY_FIELD=reply
```

Khi đó `POST /webhook/salework` sẽ trả JSON có các field `reply`, `message`, `text` để workflow map sang bước gửi tin nhắn.
