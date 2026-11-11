# AI_user_yoriqnoma

Bu vosita sayt yoki tizimni o'rganadi va **administratordan boshqa har bir foydalanuvchi roli** (oddiy foydalanuvchi, menejer, sotuv menejeri va h.k.) uchun matn va rasmli to'liq yo'riqnoma yaratadi. Rol ish boshida tanlanadi: vosita saytdagi rollarni topib, variantlar ro'yxatini chiqaradi. Ikkita **alohida** Django dasturidan iborat, repo ham shunga ko'ra ikki papkaga bo'lingan:

- **Lokal dastur** (`local/`). Foydalanuvchi kompyuterida ishlaydi va Ollama orqali yo'riqnoma yozadi. Bitta dastur, loyiha yaratishda foydalanuvchi o'zida nima borligini tanlaydi (3 rejim):
  1. **Kod + sayt linki** — kod tahlil qilinadi; xodim rollari akkauntlarini sayt egasi beradi;
  2. **Kod + sayt linki + admin login** — test foydalanuvchilarni vosita admin panelida o'zi yaratadi va ish tugagach ularni va ular yaratgan narsalarni o'chiradi;
  3. **Sayt linki + admin login (kodsiz)** — rollar admin panelidan, sahifa va vazifalar saytning o'zidan o'rganiladi; test foydalanuvchilar ham tozalanadi.

  Natija turi tanlanadi: to'liq yo'riqnoma yoki server uchun fayl (`blueprint.json` yoki `bundle.zip`).
- **Server dastur** (`server/`). Onlayn serverda alohida ishlaydi va Claude API orqali yo'riqnoma yozadi. Rejimlari: A (blueprint), A' (bundle), B (faqat URL).

Lokal va server bir-biriga ulanmaydi. Lokal dastur yaratgan faylni serverga **odam o'zi yuklaydi** (server veb-sahifasidagi forma orqali).

Batafsil hujjatlar:
- talablar — @docs/TZ.md
- tuzilma — @docs/ARCHITECTURE.md
- vazifalar tartibi — @docs/TASKS.md

## Tarkib

| Papka | Nima |
|---|---|
| `local/` | **Lokal dastur** — alohida uv loyihasi. Django + Huey (SQLite), faqat `127.0.0.1` da ishlaydi |
| `local/packages/schemas` | `yoriqnoma_schemas` — blueprint, capture va manual pydantic sxemalari (dasturlar orasidagi shartnoma) |
| `local/packages/scanner` | `yoriqnoma_scanner` — kod tahlili (SafeFS, parserlar, `scan()` → Blueprint). **Faqat lokalda** |
| `local/packages/core` | `yoriqnoma_core` — Tadqiqotchi (Playwright), Yozuvchi (LLM provayderlar), Renderer, xavfsizlik, `discovery` (kodsiz razvedka: server B, lokal 3-rejim), `provision` (admin orqali test foydalanuvchilar) |
| `local/fixtures/demo_shop` | Sinov poligoni (FastAPI + React). Integratsion testlar shu poligonda o'tadi |
| `server/` | **Server dastur** — alohida uv loyihasi. Django + DRF + Celery + Redis, PostgreSQL, MinIO, Docker |
| `server/packages/schemas`, `server/packages/core` | Lokaldagi `schemas` va `core` ning **aynan nusxasi** |
| `docs/` | TZ, arxitektura, vazifalar |

## Buyruqlar

Har bir dastur o'z papkasida, o'z `pyproject.toml`, `uv.lock` va `.venv` bilan ishlaydi. Buyruqlar shu papka ichida beriladi.

```bash
# Lokal dastur
cd local
uv sync
uv run playwright install chromium
uv run yoriqnoma-local                             # http://127.0.0.1:8765 (Windows'da: startup.bat)
uv run python manage.py <buyruq>                   # scan | explore | write | render | run | bundle | cleanup | eval
uv run demo-shop                                   # poligon: http://127.0.0.1:8800

# Server dastur
cd server
uv sync
docker compose -f docker/compose.yml up

# Tekshiruvlar — local/ va server/ ichida alohida
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python manage.py check && uv run python manage.py makemigrations --check --dry-run
uv run pytest -m "not llm and not slow and not server"
uv run pytest -m llm                               # lokalda Ollama, serverda Claude kerak
```

## Buzilmaydigan qoidalar

1. **Admin yo'q.** Administrator va adminga o'xshash rollarning (saytni boshqaradigan: foydalanuvchilar, rollar, huquqlar, sozlamalar) yo'llari va huquqlari hech qachon blueprint, capture yoki yo'riqnomaga kirmaydi. Bunday rollar uchun yo'riqnoma yozilmaydi. Noaniq rol yoki holat taqiqlanadi (default-deny).
   - **Admin login — faqat lokal 2- va 3-rejimda va faqat test foydalanuvchilar uchun** (`yoriqnoma_core.provision`). U alohida brauzer kontekstida ishlaydi: hech narsa rasmga olinmaydi va blueprint, capture yoki yo'riqnomaga kirmaydi. `ProvisionGuard` faqat foydalanuvchi yaratishga va vosita shu ishda yaratgan obyektlarni o'zgartirish yoki o'chirishga ruxsat beradi; sozlamalar, rollar, huquqlar, boshqalarning yozuvlari va ommaviy amallar bloklanadi. Admin rollari uchun foydalanuvchi yaratilmaydi.
   - Ish tugagach (xato yoki bekor qilishda ham) vosita yaratgan test foydalanuvchilar va ular yaratgan obyektlar o'chiriladi; ro'yxat `provision.json` da (parolsiz), o'chmagani hisobotga yoziladi.
   - Admin login serverga hech qachon berilmaydi va server dasturida ishlatilmaydi.
2. **Skaner fayllarni faqat `SafeFS` orqali o'qiydi.** `.env*`, kalitlar, dump'lar, `*.db`, `*.sqlite`, `*.sql` o'qilmaydi.
3. **O'rganilayotgan saytning bazasiga hech qachon ulanilmaydi.**
   - `packages/scanner` va `packages/core` da hech qanday DB drayveri yoki ORM yo'q. Buni har bir dasturdagi `tests/test_no_db_drivers.py` tekshiradi.
   - Django dasturlarining **o'z** bazasi bor: lokalda SQLite, serverda PostgreSQL. Ular faqat dasturning o'z ma'lumotlari uchun ishlatiladi.
4. **Xavfli amallar cheklangan.** O'chirish, bekor qilish va status o'zgartirish faqat test akkauntlar o'zi yaratgan obyektlar ustida bajariladi; menejer kabi rollar boshqalarning yozuvlarini ko'rsa ham, ularni o'zgartirmaydi. Production'da faqat tasdiqlash oynasigacha boriladi. To'lov faqat sandbox rejimda.
5. **Captcha avtomatik yechilmaydi.**
6. **Har bir tashqi URL `yoriqnoma_core.safety.url_guard` dan o'tadi.** Serverda `allow_private=False` majburiy.
7. **LLM chaqiruvlari faqat `LLMProvider` interfeysi orqali.** Testlarda `FakeProvider` ishlatiladi.
8. **Claude'ga boshqa shaxslarning haqiqiy ma'lumotlari yuborilmaydi.** Rasm va matnda ular to'qima test ma'lumotlariga almashtirilgan bo'ladi (12-qoida).
9. **Lokal dastur faqat `127.0.0.1` da tinglaydi.** U lokal papkalarni o'qiydi, shuning uchun tarmoqqa ochilmaydi.
10. **Lokal va server bir-biriga ulanmaydi.** Lokal dastur serverga hech narsa yubormaydi, server ham lokalga murojaat qilmaydi. `blueprint.json` yoki `bundle.zip` ni odam serverning veb-formasida yuklaydi. Ikki dastur bir-birining kodini import qilmaydi.
11. **Umumiy kutubxonalar ikki nusxada.** `schemas` va `core` `local/packages` va `server/packages` da aynan bir xil turadi. Birini o'zgartirsangiz, papkani ikkinchisiga ham ko'chiring. Buni ikkala dasturdagi `tests/test_shared_copies.py` tekshiradi. `scanner` faqat lokalda.
12. **Yo'riqnoma bitta maqsadli rol uchun, ko'rinadigan narsa xiralashtirilmaydi.** Barcha skrinshot va flow'lar shu rolning test akkaunti bilan olinadi. Rol ko'ra oladigan va qila oladigan hamma narsa rasmda aniq qoladi. Rolga tegishli bo'lmagan narsa (boshqa rollar, admin qismlari) xiralashtiriladi va matnga kirmaydi. O'z holicha ko'rsatiladi: umumiy ma'lumotlar, saytning o'z tashkilot ma'lumotlari (sayt domenidagi email, rasmiy telefon va manzil), sayt o'zi e'lon qilgan nashr kontenti (maqola, uning muallifi va rasmlari, reklama) va rolning test akkaunti o'z ma'lumotlari. **Boshqa shaxslarga tegishli ma'lumotlar** (boshqa foydalanuvchilarning yozuvlari va ular yozgan izoh, sharh, xabarlar: ism, email, telefon, manzil, karta, hujjat raqami, profil rasmi) rol ularni ko'ra olsa ham yo'riqnomaga kirmaydi: rasm va matnda ular vosita yaratgan, mavjud bo'lmagan test ma'lumotlari bilan **almashtiriladi**, atrofi aniq qoladi. Qiymat qaysi turga kirishi u turgan zonaga qarab hal qilinadi, aniqlab bo'lmasa — begona. Rasm ichidagi matn OCR bilan tekshiriladi. To'qima qiymat maxfiy kalit bilan hisoblanadi (HMAC), shuning uchun ish qayta boshlansa ham o'zgarmaydi. Begona haqiqiy qiymat faylga, logga va bundle'ga yozilmaydi.

## Konvensiyalar

- **Stek:**
  - Python 3.12, uv (har dastur — alohida workspace), pydantic v2, Playwright (async), structlog.
  - Django 5.2 LTS; HTMX + Django shablonlar (React yo'q).
  - Serverda DRF.
  - Testlar uchun pytest + pytest-django.
- **Paketlar Django'ga bog'liq emas.** `packages/*` toza Python. Django faqat dastur ilovalarida. Biznes mantiq `<ilova>/services.py` da yoziladi, view'larda emas.
- **Fon vazifalari:** lokalda Huey (SQLite storage, thread worker — Windows'da ishlaydi), serverda Celery. Playwright fon vazifasi ichida `asyncio.run(...)` bilan ishga tushiriladi, hech qachon view ichida emas.
- **Til:** kod, identifikatorlar, docstring va commit xabarlari ingliz tilida. Interfeys, yo'riqnoma matni va shablonlar o'zbek tilida (lotin). Django i18n ishlatiladi, standart til `uz`.
- **Tiplar:** type hint majburiy. Ikkala dasturda ham mypy strict (django-stubs plagini bilan).
- **Har vazifa oxirida** (o'zgargan har bir dastur papkasida):
  - testlar yashil, ruff va mypy toza;
  - migratsiyalar yaratilgan (`makemigrations --check` toza);
  - `schemas` yoki `core` o'zgargan bo'lsa, ikkinchi nusxa ham yangilangan;
  - kerak bo'lsa `docs/` yangilangan;
  - bitta mantiqiy commit;
  - qisqa hisobot: nima qilindi, nima qoldi, qanday xavf bor.
- **Sxema o'zgarganda:** `schema_version` oshiriladi, `local/` da `uv run python -m yoriqnoma_schemas.export` bilan `docs/schemas/*.json` qayta yaratiladi va `schemas` server nusxasiga ko'chiriladi.
- **Platformalar:** lokal dastur — Windows va Linux; server — Linux (Docker). Yo'llar uchun `pathlib` ishlatiladi.
- **Jim xato yo'q.** O'tkazib yuborilgan har bir narsa sababi bilan hisobotga yoziladi.
