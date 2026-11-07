# AI_user_yoriqnoma

Sayt yoki veb-tizimni o'rganib, **oddiy foydalanuvchi** uchun o'zbek tilida matn va rasmli,
qadamma-qadam yo'riqnoma yaratadigan vosita. U ikkita **alohida** dasturdan iborat:

| Papka | Dastur | Qayerda ishlaydi | Yo'riqnomani kim yozadi |
|---|---|---|---|
| [`local/`](local/) | **Lokal dastur** (Django + Huey). Kompyuterdagi loyiha kodini va saytini o'rganadi | Foydalanuvchi kompyuteri, faqat `127.0.0.1` | Ollama |
| [`server/`](server/) | **Server dastur** (Django + DRF + Celery). A, A' va B rejimlari, internetdagi saytlar bilan ishlaydi | Onlayn server (Docker) | Claude API |

Ikki dastur bir-biriga ulanmaydi. Lokal dastur `blueprint.json` yoki `bundle.zip` yaratadi,
uni serverga **odam o'zi yuklaydi** (server veb-sahifasidagi forma orqali).

Hujjatlar: [texnik topshiriq](docs/TZ.md), [arxitektura](docs/ARCHITECTURE.md), [vazifalar](docs/TASKS.md).

## Tuzilma

```
local/                    lokal dastur (alohida uv loyihasi)
  packages/schemas        blueprint, capture, manual sxemalari
  packages/scanner        kod tahlili (faqat lokalda)
  packages/core           Tadqiqotchi, Yozuvchi, Renderer, xavfsizlik
  yoriqnoma_local/        Django loyiha: sozlamalar, launcher
  projects/ runs/ settings_app/ evaluation/    Django ilovalar
  templates/ static/      HTMX sahifalar
  tests/  startup.bat
server/                   server dastur (alohida uv loyihasi)
  packages/schemas        lokaldagi nusxa
  packages/core           lokaldagi nusxa
  yoriqnoma_server/       Django loyiha: settings/{base,dev,prod,test}, celery
  accounts/ domains/ jobs/ scout/ security/ api/    Django ilovalar
  tests/
docs/                     TZ, arxitektura, vazifalar
```

`schemas` va `core` ikkala dasturda aynan bir xil nusxada turadi, shuning uchun har bir
dastur alohida o'rnatiladi. Nusxalar bir xilligini `tests/test_shared_copies.py` tekshiradi.

## Talablar

- [uv](https://docs.astral.sh/uv/). U Python 3.12 ni o'zi topadi yoki o'rnatadi.
- Lokal dastur uchun: Ollama; Node.js 20+ faqat poligonning React qismini qayta build qilish uchun.
- Server dastur uchun: Docker.

## Lokal dastur

**Windows'da tez ishga tushirish:** `local/startup.bat` faylini ikki marta bosing. U `uv` ni o'zi
topadi (PATH'da bo'lmasa ham), kutubxonalarni o'rnatadi va lokal dasturni ochadi:
`http://127.0.0.1:8765`. To'xtatish uchun oynada `Ctrl+C` bosing yoki oynani yoping.

```bash
cd local
uv sync
uv run playwright install chromium
uv run yoriqnoma-local                     # http://127.0.0.1:8765 (--dev: DEBUG rejimi)
uv run python manage.py <buyruq>           # scan | explore | write | render | run | bundle | eval
uv run demo-shop                           # poligon: http://127.0.0.1:8800
```

## Server dastur

```bash
cd server
uv sync
docker compose -f docker/compose.yml up
```

Claude API kaliti va boshqa sirlar faqat serverning o'zidagi env fayllarda turadi
(`docker/.env`, `docker/worker.env`) va git'ga tushmaydi. Batafsil: ARCHITECTURE §8.

## Tekshiruvlar

Har vazifa oxirida o'zgargan dastur papkasida (`local/` yoki `server/`) hammasi toza bo'lishi kerak:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -m "not llm and not slow and not server"
uv run pytest -m llm                       # lokalda Ollama, serverda Claude kerak
```

Git hook'lari (ixtiyoriy): `uv run --directory local pre-commit install`.

## Uchinchi tomon fayllari

- `local/static/vendor/htmx.min.js` — [htmx](https://htmx.org) 2.0.11, 0BSD litsenziyasi.
  Lokal dastur internetsiz ishlashi uchun CDN o'rniga shu nusxa ishlatiladi.
