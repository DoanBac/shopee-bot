# Huong dan dung OpenClaw voi Salework Chat

Muc tieu: dung agent dieu khien trinh duyet de doc tin nhan moi trong Salework Chat va tra loi khach Shopee.

## Nguyen tac an toan

- Chay thu che do soan nhap truoc 1-2 ngay.
- Chi auto gui cac case don gian: chao hoi, hoi chat lieu, hoi lap rap, hoi tua vit/phu kien, hoi phi ship, hoi thoi gian giao, hoi kich thuoc co trong mo ta.
- Khong auto gui case rui ro: khieu nai, hoan tien, doi tra, hang loi, thieu hang, don chua nhan, khach buc, yeu cau giam gia/boi thuong.
- Neu khong chac, chi soan nhap va dung lai de nguoi that kiem tra.

## Chuan bi

1. Cai Google Chrome hoac Microsoft Edge.
2. Dang nhap Salework Chat tren trinh duyet.
3. Dam bao tai khoan khong bat dang nhap lai lien tuc.
4. Mo file `data/salework_ai_prompt.txt`; day la prompt phong cach tra loi cua shop.
5. Neu co OpenClaw, tao task moi va dan noi dung trong `openclaw_salework_task.txt`.

## Quy trinh agent can lam

1. Mo Salework Chat.
2. Tim hoi thoai chua doc hoac co dau hieu co tin moi.
3. Mo hoi thoai.
4. Doc tin nhan moi nhat cua khach va vai tin gan nhat de lay ngu canh.
5. Khong xu ly neu tin moi nhat la tin cua shop/nhan vien.
6. Sinh cau tra loi theo `data/salework_ai_prompt.txt`.
7. Phan loai:
   - Case de: tu gui neu dang bat auto-send.
   - Case kho: chi dan vao o nhap hoac ghi chu, khong bam gui.
8. Sau moi lan gui, cho 2-5 giay va kiem tra tin da xuat hien trong chat.
9. Chuyen sang hoi thoai tiep theo.

## Cach chay khuyen nghi

Ngay 1:
- Chi cho agent soan nhap, khong bam gui.
- Ban doc lai 20-50 cau tra loi dau tien.

Ngay 2:
- Cho auto gui case de.
- Van dung lai o case khieu nai/hoan tien/loi hang/thieu hang.

Khi on dinh:
- Chay agent theo ca truc chat.
- Moi 30-60 phut kiem tra log va hoi thoai kho.

## Can dung ngay neu gap

- Salework doi giao dien lam agent khong nhan ra hoi thoai.
- Agent bam nham hoi thoai/nham nut gui.
- Khach dang khieu nai hoac tuc gian.
- Trinh duyet yeu cau dang nhap lai, captcha, OTP.

