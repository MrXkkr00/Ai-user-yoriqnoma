# AI_user_yoriqnoma

Sayt yoki veb-tizimni o'rganib, **administratordan boshqa har bir foydalanuvchi roli** (oddiy
foydalanuvchi, menejer, sotuv menejeri va h.k.) uchun o'zbek tilida matn va rasmli, qadamma-qadam
yo'riqnoma yaratadigan vosita. Saytdagi rollar topiladi va qaysi rol uchun yozish variantlardan tanlanadi. U ikkita **alohida** dasturdan iborat:

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

**Windows'da tez ishga tushirish:** `local/startup.bat` faylini ikki marta bosing. Terminal yoki
PATH sozlash kerak emas — fayl hammasini o'zi qiladi:

1. `uv` ni topadi (PATH'da bo'lmasa ham); umuman bo'lmasa, rozilik so'rab rasmiy o'rnatuvchi bilan
   o'rnatadi (PATH o'zgartirilmaydi). Python 3.12 ni ham `uv` o'zi yuklaydi.
2. Kutubxonalarni o'rnatadi yoki yangilaydi.
3. Saytni o'rganish uchun Chromium brauzerini o'rnatadi (faqat birinchi marta yuklanadi).
4. Ollama ishlamayotgan bo'lsa, uni ishga tushiradi (o'rnatilmagan bo'lsa, qayerdan olishni aytadi).
5. Dasturni `http://127.0.0.1:8765` da ochadi va brauzerni ochadi. Dastur allaqachon ishlayotgan
   bo'lsa, faqat brauzerni ochadi.

To'xtatish uchun oynada `Ctrl+C` bosing yoki oynani yoping. Ish stolida yorliq kerak bo'lsa:
faylni o'ng tugma bilan bosing → «Отправить / Send to» → «Рабочий стол / Desktop».

```bash
cd local
uv sync
uv run playwright install chromium
uv run yoriqnoma-local                     # http://127.0.0.1:8765 (--dev: DEBUG rejimi)
uv run python manage.py <buyruq>           # scan | explore | write | render | run | bundle | eval
uv run demo-shop                           # poligon: http://127.0.0.1:8800
```

### Birinchi yo'riqnoma (demo_shop misolida)

1. Ollama ishlayotganini va modelni tekshiring: `ollama pull gemma4:26b` (vision bor model).
2. Poligonni ishga tushiring: `uv run demo-shop` (alohida terminalda).
3. `uv run yoriqnoma-local` → brauzerda «Yangi loyiha»:
   - kod papkasi: `local\fixtures\demo_shop`, sayt manzili: `http://127.0.0.1:8800`;
   - pochta: «Papka», manzil: `local\fixtures\demo_shop\var\mail`.
4. «Skanerlash» → «Ko'rib chiqish» (rollar, sahifalar, flow'lar; keraksizini chiqarish mumkin).
5. «Ishga tushirish» → rol kartasini tanlang (Mijoz akkauntsiz ishlaydi; Menejer va Kuryer uchun
   loyiha sahifasida test akkaunt qo'shing: `manager@demo.local` / `Manager12345`,
   `courier@demo.local` / `Courier12345`) → «To'liq yo'riqnoma» → «Boshlash».
6. Ish sahifasida jarayon jonli ko'rinadi; tugagach HTML, PDF, DOCX va qamrov hisoboti yuklab olinadi.

Xuddi shuni terminalda ham qilish mumkin:

```bash
uv run python manage.py scan --path fixtures/demo_shop --base-url http://127.0.0.1:8800 --name demo_shop --mailbox fixtures/demo_shop/var/mail
uv run python manage.py run --project demo_shop --list-roles
uv run python manage.py run --project demo_shop --output full --role customer
```

Dastur ma'lumotlari `local/var/` da turadi (baza, Huey navbati, `secret.key`, `pseudonym.key`,
`runs/`); bu papka git'ga tushmaydi. LLM javoblari keshlanadi (`var/cache/llm`), shuning uchun
qayta yozish tez bo'ladi.

### Skaner qaysi loyihalarni o'qiydi

| Stek | Nimalar o'qiladi | Sinov loyihasi |
|---|---|---|
| FastAPI + React (Vite, React Router) | route'lar, `Depends` guard'lari, pydantic va JSX formalari, SQLAlchemy modellari, i18n JSON, Playwright E2E | `fixtures/demo_shop` |
| Flask | `Flask()` va `Blueprint(url_prefix=)` zanjiri, `@bp.route`/`@bp.get`, Flask-Login, Flask-Security rollari, `before_request` tekshiruvlari, `abort(403)`, WTForms, Jinja shablonlari (`url_for`, `_()`), Flask-SQLAlchemy modellari, Flask-Babel `.po` | test ichidagi namunalar |
| Django (+ Django REST framework) | `urls.py` (`include`, `app_name`, `re_path`, DRF router), dekorator va mixin guard'lari, `user_passes_test`, guruhlar, `LoginRequiredMiddleware`, generic view'lar, `forms.py`/`ModelForm`, serializer'lar, modellar (`TextChoices`, egasi), shablonlar (`{% url %}`, `{% trans %}`, `{{ form }}`), `.po` tarjimalar | `fixtures/demo_django` |

`demo_django` ni sinash: `cd fixtures/demo_django`, keyin
`uv run --project ../.. python manage.py migrate`, `... manage.py seed`,
`... manage.py runserver 127.0.0.1:8810` (operator akkaunti: `operator` / `Operator-pass-1`).

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
