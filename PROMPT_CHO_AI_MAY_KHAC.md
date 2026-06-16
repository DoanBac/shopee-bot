# Prompt cho AI/Codex tren may khac

Copy noi dung duoi day vao AI/Codex khi mo repo `shopee-bot` tren may moi.

```text
Ban dang lam viec trong repo shopee-bot. Muc tieu la chay bot Salework Chat auto-reply khach Shopee bang OpenClaw + Microsoft Edge + Gemini.

Hay lam theo thu tu:

1. Kiem tra repo co cac file chinh:
   - RUN_SALEWORK_BOT.ps1
   - scripts/salework_gemini_ui_bot.py
   - scripts/start_salework_gemini_bot.ps1
   - scripts/stop_salework_gemini_bot.ps1
   - scripts/start_openclaw_salework.ps1
   - scripts/start_edge_shopee_lookup.ps1
   - data/salework_ai_prompt.txt
   - .env hoac .env.example

2. Tuyet doi khong in noi dung GEMINI_API_KEY/token ra man hinh. Chi kiem tra .env co GEMINI_API_KEY hay chua.

3. Neu may moi thieu moi truong, huong dan/cai:
   - Microsoft Edge
   - Python 3.11+
   - Node.js/npm
   - OpenClaw neu chua co

4. Chay script mot nut:
   powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1

5. Neu bot da chay san va can restart:
   powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1 -Restart

6. Neu can dung bot:
   .\scripts\stop_salework_gemini_bot.ps1

7. Kiem tra log:
   Get-Content .\openclaw-logs\salework_gemini_bot.stdout.log -Tail 120 -Encoding UTF8
   Get-Content .\openclaw-logs\salework_gemini_bot.stderr.log -Tail 80 -Encoding UTF8

8. Neu OpenClaw loi gateway:
   openclaw gateway restart
   openclaw gateway status
   Sau do mo lai Salework:
   openclaw browser --browser-profile edgeremote open "https://chat.salework.net/conversations"

Rule bot hien tai:

- Chi tu tra loi case an toan:
  + khach xin video/hdsd/huong dan lap san pham
  + khach hoi kich thuoc
  + khach hoi thong tin co trong mo ta san pham

- Khong duoc tu tra loi:
  + hoan hang, hoan tien, doi tra
  + thieu oc, vit, tua vit, phu kien, thieu tam/ngan/chi tiet
  + hang loi, vo, gay, sut, me, nut, hong, sai mau
  + khach dang buc, that vong, uong tien, chat luong kem
  + phi, chi phi, phi hu, den bu, boi thuong
  + so tai khoan, chuyen khoan, Zalo, so dien thoai, Facebook, ngoai san
  + tin co hinh anh, video, file, sticker can nguoi that xem

Neu bot lo bam vao case khong duoc xu ly, phai co gang danh dau lai chua doc bang nut mat gach/mark unread de nguoi that check.

Truoc khi sua code:
- Doc scripts/salework_gemini_ui_bot.py va tests/test_salework_gemini_ui_bot.py.
- Moi rule moi phai co test moi.
- Chay:
  .\venv\Scripts\python.exe -m py_compile scripts\salework_gemini_ui_bot.py
  .\venv\Scripts\python.exe -m pytest tests\test_salework_gemini_ui_bot.py

Neu test fail thi khong bat bot.

Neu can bat bot sau khi sua:
  powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1 -Restart
```

