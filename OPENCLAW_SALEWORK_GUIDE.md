# Huong dan dung OpenClaw voi Salework Chat

Muc tieu: dung OpenClaw dieu khien Microsoft Edge de doc danh sach chat Salework va chi auto-reply cac case an toan.

## Cach chay nhanh

Chay tai thu muc repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1
```

Restart bot dang chay:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SALEWORK_BOT.ps1 -Restart
```

Dung bot:

```powershell
.\scripts\stop_salework_gemini_bot.ps1
```

## May moi can co

- Windows va Microsoft Edge.
- Python 3.11+.
- Node.js/npm neu chua co OpenClaw.
- `.env` co `GEMINI_API_KEY`.
- Da login Salework trong Edge.

Script `RUN_SALEWORK_BOT.ps1` se tu tao `venv`, cai requirements, bat OpenClaw gateway, mo Salework va mo Edge rieng de tra cuu Shopee.

## Pham vi bot duoc tu gui

- Khach xin video/hdsd/huong dan lap san pham.
- Khach hoi kich thuoc hoac thong tin nam trong mo ta san pham.
- Mot so cau thong tin san pham don gian da co rule chac chan.

## Case khong duoc tu tra loi

- Hoan hang, hoan tien, doi tra.
- Thieu oc, vit, tua vit, phu kien, thieu tam/ngan/chi tiet.
- Hang loi, vo, gay, sut, me, nut, hong, sai mau.
- Khach dang buc, that vong, noi uong tien, chat luong kem.
- Phi, chi phi, phi hu, boi thuong, den bu, so tai khoan, chuyen khoan.
- Zalo, so dien thoai, Facebook, xu ly ngoai san.
- Tin co hinh anh, video, file, sticker can nguoi that xem.

Neu lo mo chat nham case khong duoc xu ly, bot phai danh dau lai chua doc neu tim thay nut mat gach/mark unread.

## Log can xem

```powershell
Get-Content .\openclaw-logs\salework_gemini_bot.stdout.log -Tail 120 -Encoding UTF8
Get-Content .\openclaw-logs\salework_gemini_bot.stderr.log -Tail 80 -Encoding UTF8
```

## Khi gap loi

- Neu OpenClaw gateway rot: chay `openclaw gateway restart`.
- Neu Salework khong doc duoc chat: mo lai `https://chat.salework.net/conversations` trong Edge va login lai.
- Neu bot gui sai: chay `.\scripts\stop_salework_gemini_bot.ps1`, them rule/test, chay pytest roi moi bat lai.

