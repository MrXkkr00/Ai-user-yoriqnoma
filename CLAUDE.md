# AI_user_yoriqnoma

Bu vosita sayt yoki tizimni o'rganadi va **administratordan boshqa har bir foydalanuvchi roli** (oddiy foydalanuvchi, menejer, sotuv menejeri va h.k.) uchun matn va rasmli to'liq yo'riqnoma yaratadi. Rol ish boshida tanlanadi: vosita saytdagi rollarni topib, variantlar ro'yxatini chiqaradi. Ikkita **alohida** Django dasturidan iborat, repo ham shunga ko'ra ikki papkaga bo'lingan:

- **Lokal dastur** (`local/`). Foydalanuvchi kompyuterida ishlaydi. Kodni tahlil qiladi, saytni o'rganadi va Ollama orqali yo'riqnoma yozadi. Natija turi tanlanadi: to'liq yo'riqnoma yoki server uchun fayl (`blueprint.json` yoki `bundle.zip`).
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
| `local/packages/core` | `yoriqnoma_core` — Tadqiqotchi (Playwright), Yozuvchi (LLM provayderlar), Renderer, xavfsizlik |
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
uv run python manage.py <buyruq>                   # scan | explore | write | render | run | bundle | eval
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
2. **Skaner fayllarni faqat `SafeFS` orqali o'qiydi.** `.env*`, kalitlar, dump'lar, `*.db`, `*.sqlite`, `*.sql` o'qilmaydi.
3. **O'rganilayotgan saytning bazasiga hech qachon ulanilmaydi.**
   - `packages/scanner` va `packages/core` da hech qanday DB drayveri yoki ORM yo'q. Buni har bir dasturdagi `tests/test_no_db_drivers.py` tekshiradi.
   - Django dasturlarining **o'z** bazasi bor: lokalda SQLite, serverda PostgreSQL. Ular faqat dasturning o'z ma'lumotlari uchun ishlatiladi.
4. **Xavfli amallar cheklangan.** O'chirish, bekor qilish va status o'zgartirish faqat test akkauntlar o'zi yaratgan obyektlar ustida bajariladi; menejer kabi rollar boshqalarning yozuvlarini ko'rsa ham, ularni o'zgartirmaydi. Production'da faqat tasdiqlash oynasigacha boriladi. To'lov faqat sandbox rejimda.
5. **Captcha avtomatik yechilmaydi.**
6. **Har bir tashqi URL `yoriqnoma_core.safety.url_guard` dan o'tadi.** Serverda `allow_private=False` majburiy.
7. **LLM chaqiruvlari faqat `LLMProvider` interfeysi orqali.** Testlarda `FakeProvider` ishlatiladi.
8. **Claude'ga faqat maskalangan rasm va matn yuboriladi** (haqiqiy odamlarning shaxsiy ma'lumotlari yashirilgan, 12-qoida).
9. **Lokal dastur faqat `127.0.0.1` da tinglaydi.** U lokal papkalarni o'qiydi, shuning uchun tarmoqqa ochilmaydi.
10. **Lokal va server bir-biriga ulanmaydi.** Lokal dastur serverga hech narsa yubormaydi, server ham lokalga murojaat qilmaydi. `blueprint.json` yoki `bundle.zip` ni odam serverning veb-formasida yuklaydi. Ikki dastur bir-birining kodini import qilmaydi.
11. **Umumiy kutubxonalar ikki nusxada.** `schemas` va `core` `local/packages` va `server/packages` da aynan bir xil turadi. Birini o'zgartirsangiz, papkani ikkinchisiga ham ko'chiring. Buni ikkala dasturdagi `tests/test_shared_copies.py` tekshiradi. `scanner` faqat lokalda.
12. **Yo'riqnoma bitta maqsadli rol uchun, ko'rinadigan narsa xiralashtirilmaydi.** Barcha skrinshot va flow'lar shu rolning test akkaunti bilan olinadi. Rol ko'ra oladigan va qila oladigan hamma narsa rasmda aniq qoladi. Rolga tegishli bo'lmagan narsa (boshqa rollar, admin qismlari) xiralashtiriladi va matnga kirmaydi. Istisno: haqiqiy odamlarning shaxsiy ma'lumotlari (email, telefon, karta, ism) — faqat qiymatning o'zi yashiriladi; vosita yaratgan test ma'lumotlari yashirilmaydi.

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
