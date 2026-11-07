# AI_user_yoriqnoma

Sayt yoki veb-tizimni o'rganib, **oddiy foydalanuvchi** uchun o'zbek tilida matn va rasmli,
qadamma-qadam yo'riqnoma yaratadigan vosita. Saytni kodi orqali yoki faqat URL orqali o'rganadi.

## Tarkib

| Papka | Nima |
|---|---|
| `packages/schemas` | `yoriqnoma_schemas` — blueprint, capture va manual sxemalari (dasturlar orasidagi shartnoma) |
| `packages/scanner` | `yoriqnoma_scanner` — kod tahlili: `SafeFS`, parserlar, `scan()` → Blueprint |
| `packages/core` | `yoriqnoma_core` — Tadqiqotchi (Playwright), Yozuvchi (LLM), Renderer, xavfsizlik |
| `apps/local` | **Lokal dastur** (Django + Huey). Faqat `127.0.0.1` da ishlaydi, yo'riqnomani Ollama bilan yozadi |
| `apps/server` | **Server dastur** (Django + DRF + Celery). A, A' va B rejimlari, yo'riqnomani Claude API bilan yozadi |
| `docs/` | [Texnik topshiriq](docs/TZ.md), [arxitektura](docs/ARCHITECTURE.md), [vazifalar](docs/TASKS.md) |

Paketlar toza Python va Django'ga bog'liq emas. Django faqat `apps/*` ichida.

## Talablar

- [uv](https://docs.astral.sh/uv/). U Python 3.12 ni o'zi topadi yoki o'rnatadi.
- Node.js 20+ — faqat poligonning React qismini qayta build qilish uchun.
- Ollama — lokal dastur yo'riqnoma yozishi uchun.
- Docker — server dastur uchun.

## Buyruqlar

```bash
uv sync --all-packages                     # barcha paketlar va dev vositalar
uv run playwright install chromium
uv run demo-shop                           # poligon: http://127.0.0.1:8800
uv run yoriqnoma-local                     # lokal dastur: http://127.0.0.1:8765 (--dev: DEBUG rejimi)
uv run python apps/local/manage.py <buyruq>    # scan | explore | write | render | run | bundle | eval
docker compose -f docker/compose.yml up    # server dastur
```

Tekshiruvlar (har vazifa oxirida hammasi toza bo'lishi kerak):

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy                                # packages/ (strict) va tests/
uv run --directory apps/local mypy         # lokal dastur (django-stubs)
uv run --directory apps/server mypy        # server dastur (django-stubs + DRF)
uv run python apps/local/manage.py check
uv run python apps/server/manage.py check
uv run python apps/local/manage.py makemigrations --check --dry-run
uv run python apps/server/manage.py makemigrations --check --dry-run
uv run pytest -m "not llm and not slow and not server"               # paketlar va tests/
uv run pytest apps/local -m "not llm and not slow and not server"    # lokal dastur
uv run pytest apps/server -m "not llm and not slow and not server"   # server dastur
uv run pytest -m llm                       # Ollama yoki Claude kerak
```

Ikki Django loyihasini bitta Python jarayonida sinab bo'lmaydi, chunki Django sozlamalari global.
Shuning uchun `pytest` va `mypy` har bir dastur uchun alohida ishga tushiriladi.
Har bir dasturning sozlamasi o'zining `pyproject.toml` faylida turadi.

Git hook'lari (ixtiyoriy): `uv run pre-commit install`.

## Uchinchi tomon fayllari

- `apps/local/static/vendor/htmx.min.js` — [htmx](https://htmx.org) 2.0.11, 0BSD litsenziyasi.
  Lokal dastur internetsiz ishlashi uchun CDN o'rniga shu nusxa ishlatiladi.
