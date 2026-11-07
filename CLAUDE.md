# AI_user_yoriqnoma

Bu vosita sayt yoki tizimni o'rganadi va **oddiy foydalanuvchi** uchun matn va rasmli to'liq yo'riqnoma yaratadi. Ikkita Django dasturidan iborat:

- **Lokal dastur** (`apps/local`). Kodni tahlil qiladi, saytni o'rganadi va Ollama orqali yo'riqnoma yozadi. Natija turi tanlanadi: to'liq yo'riqnoma yoki server uchun ma'lumot (blueprint yoki bundle).
- **Server dastur** (`apps/server`). Onlayn ishlaydi va Claude API orqali yo'riqnoma yozadi. Rejimlari: A (blueprint), A' (bundle), B (faqat URL).

Batafsil hujjatlar:
- talablar — @docs/TZ.md
- tuzilma — @docs/ARCHITECTURE.md
- vazifalar tartibi — @docs/TASKS.md

## Tarkib

| Papka | Nima |
|---|---|
| `packages/schemas` | `yoriqnoma_schemas` — blueprint, capture va manual pydantic sxemalari (dasturlar orasidagi yagona shartnoma) |
| `packages/scanner` | `yoriqnoma_scanner` — kod tahlili kutubxonasi (SafeFS, parserlar, `scan()` → Blueprint) |
| `packages/core` | `yoriqnoma_core` — Tadqiqotchi (Playwright), Yozuvchi (LLM provayderlar), Renderer, xavfsizlik |
| `apps/local` | Lokal Django dasturi: Huey (SQLite), faqat `127.0.0.1` da ishlaydi |
| `apps/server` | Server Django dasturi: DRF, Celery + Redis, PostgreSQL, MinIO, Docker |
| `fixtures/demo_shop` | Sinov poligoni (FastAPI + React). Barcha integratsion testlar shu poligonda o'tadi |

## Buyruqlar

```bash
uv sync --all-packages
uv run playwright install chromium
uv run demo-shop                                   # poligon: http://127.0.0.1:8800
uv run yoriqnoma-local                             # lokal dastur: http://127.0.0.1:8765 (web + huey)
uv run python apps/local/manage.py <buyruq>        # scan | explore | write | render | run | bundle | eval
docker compose -f docker/compose.yml up            # server dastur
uv run pytest -m "not llm and not slow and not server"
uv run pytest -m llm                               # Ollama yoki Claude kerak
uv run ruff check . && uv run ruff format --check .
uv run mypy packages apps
```

## Buzilmaydigan qoidalar

1. **Admin yo'q.** O'rganilayotgan saytning admin yo'llari va huquqlari hech qachon blueprint, capture yoki yo'riqnomaga kirmaydi. Noaniq holat taqiqlanadi (default-deny).
2. **Skaner fayllarni faqat `SafeFS` orqali o'qiydi.** `.env*`, kalitlar, dump'lar, `*.db`, `*.sqlite`, `*.sql` o'qilmaydi.
3. **O'rganilayotgan saytning bazasiga hech qachon ulanilmaydi.**
   - `packages/scanner` va `packages/core` da hech qanday DB drayveri yoki ORM yo'q. Buni `tests/test_no_db_drivers.py` tekshiradi.
   - Django dasturlarining **o'z** bazasi bor: lokalda SQLite, serverda PostgreSQL. Ular faqat dasturning o'z ma'lumotlari uchun ishlatiladi.
4. **Xavfli amallar cheklangan.** O'chirish va bekor qilish faqat test user o'zi yaratgan obyektlar ustida bajariladi. Production'da faqat tasdiqlash oynasigacha boriladi. To'lov faqat sandbox rejimda.
5. **Captcha avtomatik yechilmaydi.**
6. **Har bir tashqi URL `yoriqnoma_core.safety.url_guard` dan o'tadi.** Serverda `allow_private=False` majburiy.
7. **LLM chaqiruvlari faqat `LLMProvider` interfeysi orqali.** Testlarda `FakeProvider` ishlatiladi.
8. **Claude'ga faqat maskalangan rasm va matn yuboriladi.**
9. **Lokal dastur faqat `127.0.0.1` da tinglaydi.** U lokal papkalarni o'qiydi, shuning uchun tarmoqqa ochilmaydi.

## Konvensiyalar

- **Stek:**
  - Python 3.12, uv workspace, pydantic v2, Playwright (async), structlog.
  - Django 5.2 LTS; HTMX + Django shablonlar (React yo'q).
  - Serverda DRF.
  - Testlar uchun pytest + pytest-django.
- **Paketlar Django'ga bog'liq emas.** `packages/*` toza Python. Django faqat `apps/*` da. Biznes mantiq `apps/*/<app>/services.py` da yoziladi, view'larda emas.
- **Fon vazifalari:** lokalda Huey (SQLite storage, thread worker — Windows'da ishlaydi), serverda Celery. Playwright fon vazifasi ichida `asyncio.run(...)` bilan ishga tushiriladi, hech qachon view ichida emas.
- **Til:** kod, identifikatorlar, docstring va commit xabarlari ingliz tilida. Interfeys, yo'riqnoma matni va shablonlar o'zbek tilida (lotin). Django i18n ishlatiladi, standart til `uz`.
- **Tiplar:** type hint majburiy. `packages/` uchun mypy strict, `apps/` uchun django-stubs.
- **Har vazifa oxirida:**
  - testlar yashil, ruff va mypy toza;
  - migratsiyalar yaratilgan (`makemigrations --check` toza);
  - kerak bo'lsa `docs/` yangilangan;
  - bitta mantiqiy commit;
  - qisqa hisobot: nima qilindi, nima qoldi, qanday xavf bor.
- **Sxema o'zgarganda:** `schema_version` oshiriladi va `uv run python -m yoriqnoma_schemas.export` bilan `docs/schemas/*.json` qayta yaratiladi.
- **Platformalar:** lokal dastur — Windows va Linux; server — Linux (Docker). Yo'llar uchun `pathlib` ishlatiladi.
- **Jim xato yo'q.** O'tkazib yuborilgan har bir narsa sababi bilan hisobotga yoziladi.
