# demo_shop — sinov poligoni

Kichik do'kon sayti: FastAPI + SQLite (o'z bazasi) va React (Vite, React Router v6).
Barcha integratsion testlar shu saytda o'tadi (ARCHITECTURE §10).

## Ishga tushirish

```bash
cd local
uv run demo-shop            # http://127.0.0.1:8800
uv run demo-shop --reset    # bazani o'chirib, qayta seed qilish
```

Pochta: `MAILPIT_SMTP=127.0.0.1:1025` bo'lsa Mailpit'ga, bo'lmasa `var/mail/*.eml` ga yoziladi.

Frontend o'zgarsa: `cd web && npm install && npm run build` (`web/dist` repoga commit qilinadi).

## Rollar va test akkauntlar

| Rol | Akkaunt | Sahifalar |
|---|---|---|
| `customer` | o'zi ro'yxatdan o'tadi | `/app/*` |
| `manager` | `manager@demo.local` / `Manager12345` | `/staff/orders` |
| `courier` | `courier@demo.local` / `Courier12345` | `/courier` |
| `admin` | `admin@demo.local` / `Admin12345` | `/admin*` — yo'riqnomaga kirmasligi kerak |

## FR-E10 sinov ma'lumotlari

- footer: `info@demo-shop.uz`, `+998 71 200-00-00` — tashkilot ma'lumoti, o'z holicha qoladi;
- `/catalog/1` sharhlari (Jasur Toshmatov, Malika Yusupova) — almashtiriladi;
- Dilnoza Karimova buyurtmalari (menejer va kuryer ko'radi) — almashtiriladi;
- 1-buyurtmaning yetkazish varaqasi rasmi (ism va telefon rasm ichida) — OCR bilan xiralashtiriladi.

## Skaner uchun tuzoqlar

`.env` (soxta sirlar) va `var/demo.db`: **skaner ularni ochmasligi kerak**.
