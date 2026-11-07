# Claude Code uchun vazifalar ketma-ketligi

Bu faylda loyihani noldan qurish uchun Claude Code'ga **ketma-ket** yuboriladigan tayyor promptlar bor. Har bir vazifa kichik va tekshiriladigan qilib bo'lingan.

**Yakuniy natija — ikkita Django dasturi:**
- **Lokal dastur** (`local/`) — skan, tadqiqot, Ollama orqali yozish. Natija turi tanlanadi: to'liq yo'riqnoma, blueprint yoki bundle.
- **Server dastur** (`server/`) — onlayn, Claude API, A / A' / B rejimlari.

Har biri o'z `packages/` papkasidagi kutubxonalar ustiga quriladi: `schemas` va `core` ikkalasida bir xil nusxa, `scanner` faqat lokalda.

**Qurish tartibi:**
1. Avval umumiy paketlar: F0–F3.
2. Keyin lokal dastur: F4.
3. Keyin server: F5–F6.

**Repo tuzilmasi (2026-11-07 dan).** Repo ikki mustaqil papkaga bo'lingan: `local/` va `server/`. Har biri o'z `pyproject.toml`, `uv.lock` va `.venv` bilan alohida ishlaydi. Quyidagi vazifalarda eski yo'llar uchrasa, ularni shu jadval bo'yicha o'qing:

| Vazifadagi yo'l | Hozirgi joyi |
|---|---|
| `apps/local/...` | `local/...` |
| `apps/server/...` | `server/...` |
| `packages/schemas`, `packages/core` | `local/packages/...` **va** `server/packages/...` — ikkita bir xil nusxa, ikkalasini ham yangilang (`tests/test_shared_copies.py` tekshiradi) |
| `packages/scanner` | `local/packages/scanner` (faqat lokalda) |
| `tests/` (workspace testlari) | `local/tests/` va `server/tests/` |
| `fixtures/demo_shop` | `local/fixtures/demo_shop` |
| `docker/` | `server/docker/` |
| `uv run pytest apps/local`, `uv run --directory apps/server mypy` va h.k. | dastur papkasida `uv run pytest`, `uv run mypy` |

Lokal dastur serverga ulanmaydi: blueprint va bundle serverga odam orqali o'tadi (T25). Serverda API kalitlar yo'q.

## 0. Boshlashdan oldin (o'zingiz bajarasiz)

1. **O'rnating:**
   - Git;
   - [uv](https://docs.astral.sh/uv/) (Python'ni o'zi o'rnatadi: `uv python install 3.12`);
   - Node.js 20+ (faqat poligonning React qismini build qilish uchun);
   - Ollama;
   - Mailpit (Windows binary yoki Docker);
   - Docker Desktop (F5 dan boshlab, server dasturi uchun);
   - Claude Code.
2. **Ollama modellarini yuklang:** `ollama pull gemma4:26b` va `ollama pull qwen3.6:27b`.
3. **Repo papkasini tayyorlang:**
   - bo'sh `ai-user-yoriqnoma` papkasini yarating;
   - bu to'plamdagi `CLAUDE.md` va `docs/` ni unga ko'chiring;
   - `git init` qiling va birinchi commit'ni bajaring.
4. **Claude Code'ni ishga tushiring:** papkada `claude` buyrug'ini bering.

## Ish tartibi

- **Har bir vazifa — yangi toza sessiya.** Oldingi vazifa tugagach, `/clear` buyrug'ini bering yoki `claude` ni qayta ishga tushiring. `CLAUDE.md` har safar avtomatik yuklanadi.
- **"Rejim: plan" deb belgilangan vazifalar:**
  1. `Shift+Tab` ni status qatorida `⏸ plan mode on` chiqquncha bosing yoki sessiyani `claude --permission-mode plan` bilan oching.
  2. Promptni yuboring.
  3. Claude taklif qilgan rejani o'qing. Kerak bo'lsa tuzating, keyin tasdiqlang.
- **Prompt matnini to'liq nusxalang.** `@fayl` havolalari kerakli hujjatni kontekstga qo'shadi.
- **Har vazifadan keyin:**
  1. "Qabul mezoni"ni o'zingiz tekshiring: testlarni ishga tushiring, natijani ko'ring.
  2. Mezon bajarilmasa, keyingisiga o'tmang. Pastdagi "Tuzatish" shablonini ishlating.
  3. Commit borligini tekshiring (`git log -1`).
- **Har faza oxirida** "Faza tekshiruvi" promptini yuboring.

### Yordamchi shablonlar

**Tuzatish:**
```
Oxirgi vazifa (Txx) qabul mezoni bajarilmadi: <nima bo'lganini yoz, xato matnini qo'sh>.
Sababini top, tuzat, tegishli test qo'sh (regressiya), barcha testlarni qayta ishga tushir. Commit qil.
```

**Faza tekshiruvi:**
```
@docs/TZ.md @docs/TASKS.md
Fx fazasi tugadi. Shu fazaga tegishli TZ talablarini (FR-/SEC- raqamlari) bitta-bitta tekshir:
qaysi biri bajarilgan (fayl/test bilan isbotla), qaysi biri qisman yoki bajarilmagan.
Barcha testlarni, ruff va mypy'ni ishga tushir. Natijani jadval qilib ber va bajarilmaganlar
uchun qisqa tuzatish rejasini taklif qil. Hech narsani o'zgartirma — faqat hisobot.
```

**Hujjat yangilash** (arxitektura o'zgarsa):
```
Hozirgi kodga qarab @docs/ARCHITECTURE.md ni yangila: faqat haqiqatda o'zgargan joylarni.
Nima o'zgarganini qisqa yoz. Commit: "docs: sync architecture".
```

---

## F0 — Asos

### T00 — Repo skeleti va vositalar

Rejim: plan

```
@CLAUDE.md @docs/ARCHITECTURE.md (1-bo'lim) ni o'qi.
Vazifa: uv workspace skeletini yarat — 3 ta kutubxona paketi va 2 ta Django dasturi.

- Ildiz pyproject.toml: workspace a'zolari packages/schemas, packages/scanner, packages/core,
  apps/local, apps/server; ruff (line-length 100, isort, pyupgrade, bugbear, django qoidalari),
  mypy (packages/* strict; apps/* uchun django-stubs plagini), pytest (markerlar: llm, slow, server;
  asyncio_mode=auto; pytest-django).
- packages/*: pyproject.toml (hatchling), src/<nom>/__init__.py, tests/test_smoke.py.
  Bog'liqliklar ARCHITECTURE 1-bo'limdagi jadvalga mos. Paketlarda Django YO'Q.
- apps/local: Django 5.2 loyiha (yoriqnoma_local), bo'sh ilovalar projects, runs, settings_app,
  uploader, evaluation; SQLite var/local.sqlite3; LANGUAGE_CODE="uz", TIME_ZONE="Asia/Tashkent";
  ALLOWED_HOSTS faqat 127.0.0.1/localhost; huey (SqliteHuey) ulangan; entry point yoriqnoma-local
  (hozircha runserver 127.0.0.1:8765 ni ishga tushiradi); "Salom" bosh sahifasi (base.html + HTMX ulangan).
- apps/server: Django 5.2 loyiha (yoriqnoma_server), settings/{base,dev,prod}.py (django-environ),
  bo'sh ilovalar accounts, domains, jobs, scout, security, api; DRF o'rnatilgan; celery.py;
  Django admin /ops/ da; dev uchun SQLite, prod uchun DATABASE_URL.
- tests/test_no_db_drivers.py: packages/scanner va packages/core MANBA KODIDA (ast, barcha .py)
  sqlite3, psycopg, psycopg2, pymysql, sqlalchemy, sqlmodel, asyncpg, aiosqlite, django importi yo'qligini
  va pyproject bog'liqliklarida ham yo'qligini tekshirsin.
- .gitignore (var/, .cache/, dist/, .venv/, node_modules/, *.sqlite3), .pre-commit-config.yaml
  (ruff, ruff-format), .github/workflows/ci.yml (ubuntu + windows: uv sync, ruff, mypy,
  manage.py check, makemigrations --check, pytest -m "not llm and not slow and not server").
- README.md: qisqa tavsif va CLAUDE.md dagi buyruqlar.

Tekshir: uv sync --all-packages, uv run pytest, ruff, mypy, ikkala dasturda manage.py check — hammasi toza.
Commit: "chore: workspace skeleton with local and server django projects".
```

**Qabul mezoni:**
- `uv run pytest` yashil.
- `uv run yoriqnoma-local` brauzerda `http://127.0.0.1:8765` da bosh sahifani ochadi.
- `apps/server` da `manage.py runserver` ishlaydi.

### T01 — Sxemalar paketi

Rejim: plan

```
@docs/ARCHITECTURE.md (3-bo'lim) @docs/TZ.md (2, 7-bo'limlar)
Vazifa: packages/schemas da yoriqnoma_schemas paketini to'liq yoz.

- common.py, policy.py, blueprint.py, capture.py, manual.py — ARCHITECTURE 3-bo'limdagi modellar,
  extra="forbid", schema_version="1.0".
- Validatorlar: Flow.requires mavjud id'larga ishora qiladi; requires grafi sikl'siz
  (sikl bo'lsa xabarda sikl yo'lini ko'rsat); Target kamida bitta maydonli; pages ichida
  role="excluded" yo'q; Policy.deny_paths glob formatida.
- Yordamchilar: Blueprint.topo_order() -> list[Flow]; Blueprint.content_hash();
  CaptureRun.state_by_id(); load_json/save_json (UTF-8, indent=2, ensure_ascii=False).
- export.py: `python -m yoriqnoma_schemas.export` -> docs/schemas/{blueprint,capture,manual}.schema.json.
- docs/schemas/examples/ ga har sxema uchun bitta to'liq, real ko'rinishdagi namuna
  (demo_shop'ga mos: buyurtma obyekti, statuslar, 3-4 flow).
- Testlar: namunalar validatsiyadan o'tadi; noto'g'ri namunalar (sikl, noma'lum requires,
  extra maydon) aniq xato beradi; topo_order to'g'ri; round-trip (save -> load) teng.

Commit: "feat(schemas): blueprint, capture, manual models".
```

**Qabul mezoni:** testlar yashil. `docs/schemas/*.json` fayllari yaratilgan.

### T02 — Poligon: demo_shop

Rejim: plan

```
@docs/ARCHITECTURE.md (10-bo'lim) ni diqqat bilan o'qi.
Vazifa: fixtures/demo_shop poligonini yarat. Bu sinov sayti — barcha keyingi integratsion testlar shunda.

- Backend: FastAPI + SQLite (o'z bazasi, var/demo.db), sessiya cookie auth, rollar user/admin.
  10-bo'limdagi barcha user va admin yo'llari, statuslar mashinasi, validatsiya qoidalari.
  Admin endpointlar `Depends(require_admin)` bilan. Seed: 1 admin (admin@demo.local), 10 mahsulot,
  boshqa userga tegishli 3 ta buyurtma (vosita ularni HECH QACHON ko'rmasligi kerak).
- Pochta: SMTP (MAILPIT_SMTP=127.0.0.1:1025) bo'lsa Mailpit'ga, bo'lmasa var/mail/*.eml.
  Tasdiqlash xati ichida havola va 6 xonali kod.
- Frontend: web/ papkada React + Vite + React Router v6. Sahifalar 10-bo'limdagidek; order sahifasida
  tablar va bekor qilish modali; <RequireAuth> va <RequireAdmin> guard komponentlari; NavBar;
  i18n (web/src/locales/uz.json, ru.json, oddiy t() funksiya); formalarda label, name, required,
  minLength, pattern atributlari; data-testid ba'zi elementlarda bor, ba'zilarida yo'q (realistik).
  `npm run build` natijasi (web/dist) repoga commit qilinsin; FastAPI uni / da beradi (SPA fallback).
- E2E: e2e/test_register.py (Playwright Python) va e2e/order.spec.ts (Playwright TS) — ro'yxatdan o'tish
  va buyurtma yaratish/bekor qilish.
- Tuzoqlar: .env (SECRET_KEY=fake..., DATABASE_URL=sqlite:///var/demo.db), README'da "skaner buni ochmasligi kerak".
- `uv run demo-shop` (port 8800, --reset bilan bazani qayta yaratadi).
- tests/: pytest fixture `demo_shop_url` (subprocess'da ishga tushiradi, tayyor bo'lishini kutadi, oxirida o'chiradi);
  smoke test: barcha user sahifalari 200, /admin oddiy user uchun 403/redirect.

Muhim: demo_shop o'zi SQLite ishlatadi — bu ruxsat (u bizning vosita emas). Lekin u yoriqnoma_core
yoki yoriqnoma_scanner'ga import qilinmasin.
Commit: "feat(fixtures): demo_shop test site".
```

**Qabul mezoni:**
- `uv run demo-shop` ishlaydi.
- Brauzerda ro'yxatdan o'tish → tasdiqlash → buyurtma yaratish jarayonini qo'lda o'tkazib ko'ring.
- Smoke testlar yashil.

---

## F1 — Skaner paketi (`packages/scanner`)

### T03 — Skaner asosi: SafeFS, stekni aniqlash

```
@CLAUDE.md @docs/TZ.md (4.1, SEC-3) @docs/ARCHITECTURE.md (1, 4.2)
Vazifa: packages/scanner (yoriqnoma_scanner kutubxonasi) asosini yoz. Django'ga bog'liq emas.

- fs_guard.py: SafeFS(root) — TZ SEC-3 dagi taqiqlangan naqshlar (konfiguratsiyalanadigan, lekin
  standart ro'yxatni kamaytirib bo'lmaydi), 2 MB limit, binar fayllarni aniqlash, symlink orqali
  root'dan chiqishni bloklash, skipped ro'yxati (yo'l + sabab, fayl mazmunisiz).
- detect.py: ProjectInfo (root, stacks: set[str], frontend_dirs, backend_dirs, e2e_dirs, locales) —
  pyproject/requirements, package.json, fayl naqshlari bo'yicha. MVP: "fastapi", "react", "react-router",
  "vite", "playwright-py", "playwright-ts".
- ast_utils.py: tree-sitter (tree-sitter-language-pack) yuklash, python/javascript/typescript/tsx parserlari,
  .vue fayldan <script> blokini ajratish yordamchisi, node matni va qator raqami.
- parsers/base.py: Parser protokoli va ParseResult (ARCHITECTURE 4.2).
- api.py: scan(project_dir, base_url, stack="auto") -> ScanResult — hozircha detect natijasi va
  skipped ro'yxatini qaytaradi (blueprint T08 da).
- __main__.py (debug): python -m yoriqnoma_scanner PATH --base-url URL [--out] [--report] — natijani chiqaradi.
- Testlar: SafeFS .env, *.pem, var/demo.db, node_modules ni o'qimaydi; builtins.open'ni kuzatuvchi
  test — demo_shop skan qilinganda .env HECH QACHON ochilmaydi; symlink testi (Windows'da skip mumkin);
  detect demo_shop'da fastapi+react+playwright topadi.

Commit: "feat(scanner): safe fs, stack detection".
```

**Qabul mezoni:** `uv run python -m yoriqnoma_scanner fixtures/demo_shop --base-url http://127.0.0.1:8800` steklarni to'g'ri ko'rsatadi. `.env` testi yashil.

### T04 — FastAPI parseri

```
@docs/TZ.md (FR-S3, FR-S4) @docs/ARCHITECTURE.md (3.3, 4.2)
Vazifa: parsers/fastapi_routes.py va parsers/pydantic_forms.py.

- Route'lar: @app/@router.get/post/put/patch/delete, APIRouter(prefix=...), include_router(prefix=...)
  zanjirini hisobga olib to'liq yo'l; path parametrlari.
- Guard'lar: Depends(...) va dependencies=[...] dagi funksiya nomlari va ularning tanasi
  (bir daraja chuqur): require_admin, get_current_superuser, is_admin, role == "admin",
  user.is_staff -> kind="role"; get_current_user -> "auth"; obj.owner_id == user.id kabi
  tekshiruvlar -> "ownership"; tushunarsiz -> "unknown".
- Pydantic so'rov modellari -> FormField: tip (EmailStr -> email, SecretStr/"password" -> password),
  Field(min_length, max_length, ge, le, pattern) -> rules.
- Testlar: tests/fixtures/snippets/fastapi/ ichida kichik namunalar (prefix zanjiri, admin dependency,
  ownership, noma'lum guard) + demo_shop'da barcha /api yo'llari va /api/admin* ning role guard'i topiladi.

Commit: "feat(scanner): fastapi routes and pydantic forms".
```

**Qabul mezoni:** demo_shop'dagi barcha API yo'llari topilgan, admin yo'llari `kind=role` guard bilan.

### T05 — React parseri

```
@docs/TZ.md (FR-S3) @docs/ARCHITECTURE.md (4.2, 10)
Vazifa: parsers/react_router.py, parsers/jsx_forms.py, parsers/zod_yup.py, parsers/i18n.py.

- React Router v6: createBrowserRouter([...]) obyektlari va <Routes><Route path element> JSX,
  ichma-ich route'lar (to'liq yo'l), index route'lar, lazy importlar.
- Guard: route element'ini o'rab turgan komponent nomi (RequireAdmin, AdminRoute, ProtectedRoute
  role="admin" -> role; RequireAuth -> auth). Komponent tanasida role tekshiruvi bo'lsa ham "role".
- Navigatsiya: <Link>/<NavLink to> va ularning matni yoki t('key') -> nav ro'yxati.
- Formalar: <form> ichidagi input/select/textarea — name, type, label (htmlFor yoki o'rab turgan
  <label>), required, minLength, maxLength, pattern, min, max; submit tugmasi matni; onSubmit ichidagi
  fetch/axios chaqiruvidan API yo'li (aniqlansa).
- zod/yup sxemalari -> rules.
- i18n: locales/*.json (nested kalitlarni tekislash), t('a.b') ni matnga almashtirish.
- Testlar: snippet namunalari + demo_shop: barcha /app/* sahifalari, /admin* RequireAdmin bilan,
  register formasi maydonlari va qoidalari, nav ro'yxati o'zbekcha matnlar bilan.

Commit: "feat(scanner): react router, jsx forms, i18n".
```

**Qabul mezoni:** demo_shop'ning barcha frontend sahifalari va formalari topilgan, label'lar o'zbekcha.

### T06 — Obyektlar, amallar va statuslar

```
@docs/TZ.md (FR-S5) @docs/ARCHITECTURE.md (3.3)
Vazifa: parsers/sqlalchemy_models.py va entities.py.

- SQLAlchemy/SQLModel modellari (faqat KOD sifatida, AST orqali; hech qanday import/ulanish yo'q):
  jadval nomi, user'ga FK (user_id/owner_id/author_id) -> owner_field, Enum status maydonlari va qiymatlari.
- API route'lar bilan bog'lash: /orders POST -> create, GET list/{id} -> list/view, PUT/PATCH -> update,
  DELETE -> delete, POST /orders/{id}/<fe'l> -> maxsus amal (<fe'l>).
- Status o'tishlari: route handler'larida `obj.status = Status.X` topilsa, X ni o'sha route'ning
  roli bilan bog'la. X faqat role-guard'li (admin) route'larda o'rnatilsa -> reachable_by_user=False,
  set_by ga manbalarni yoz.
- Testlar: demo_shop'da Order obyekti: actions = create, list, view, cancel, pay, download_invoice;
  statuslar new/paid/cancelled reachable=True, shipped/delivered reachable=False.

Commit: "feat(scanner): entities, actions and status reachability".
```

**Qabul mezoni:** `shipped` va `delivered` statuslari `reachable_by_user=false`.

### T07 — E2E testlardan flow'lar

```
@docs/ARCHITECTURE.md (3.3 Step, Target)
Vazifa: parsers/e2e_playwright_py.py va parsers/e2e_playwright_ts.py.

- page.goto, get_by_role(role, name=...), get_by_label, get_by_test_id, get_by_text, locator(css),
  .click(), .fill(value), .select_option, .check, expect(page).to_have_url, expect(...).to_have_text/
  to_be_visible -> Step'lar (Target bilan).
- fill qiymatlari: email ko'rinishidagi -> "fake:email", parolga o'xshash -> "fake:password", telefon ->
  "fake:phone_uz", ism -> "fake:full_name", boshqalar -> "literal:...".
- Har test funksiyasi / test() bloki -> Flow (title test nomidan, source fayl:qator, confidence=1.0).
- Admin sahifalariga goto qiladigan testlar butunlay tashlanadi (sababi bilan notes ga).
- Testlar: demo_shop'ning e2e/ fayllaridan kamida 2 flow to'g'ri qadamlar bilan.

Commit: "feat(scanner): flows from playwright e2e tests".
```

### T08 — Tasniflash, flow'lar yig'uvchisi, blueprint va hisobot

Rejim: plan

```
@docs/TZ.md (4.1 to'liq, SEC-1/2) @docs/ARCHITECTURE.md (3.2, 3.3)
Vazifa: classify.py, flows.py, build.py, report.py, overrides.py va api.scan() ni yakunlash.

- classify: route rolini aniqlash. Tartib: deny_paths -> excluded; role guard -> excluded;
  guard yo'q va ochiq sahifa -> guest; auth/ownership -> user; unknown -> excluded (default-deny).
  Frontend va backend ma'lumotlarini birlashtir (sahifa yo'li + u chaqiradigan API).
  Har qaror uchun reason.
- flows: (1) E2E flow'lar; (2) hisob flow'lari: register, verify_email, login, forgot_password,
  profile_edit, settings, delete_account — mavjud sahifa/formalarga qarab; (3) har Entity × action uchun
  flow (create: form'ni to'ldirish; view/list: goto; cancel/delete: tasdiqlash modali bilan,
  destructive=True; pay: payment=True). E2E bilan bir xil flow bo'lsa E2E ustun.
  requires: register -> barcha user flow'lar; create -> view/update/cancel/pay/delete;
  delete_account -> hammasi (oxirida). stage avtomatik (ARCHITECTURE Stage).
  social flow'lar (messages) account="B" ishtirokida.
- build: Blueprint yig'ish, policy (standart deny_paths + deny_action_words uz/ru/en),
  generator="yoriqnoma_scanner <versiya>", validatsiya.
- report.md: statistika, sahifalar jadvali (rol, sabab), chiqarib tashlanganlar, noaniqlar,
  SafeFS skipped ro'yxati, obyektlar va statuslar.
- overrides.py: apply(blueprint, overrides) — {"exclude_pages", "exclude_flows", "rename_flows"};
  faqat KAMAYTIRADI (excluded'dagi narsani qaytara olmaydi), chiqarilgan flow'ga bog'liq flow'lar ham
  avtomatik chiqariladi (sabab bilan). Lokal dasturdagi "ko'rib chiqish" sahifasi shuni ishlatadi.
- api.scan() -> ScanResult(blueprint, report_md, skipped, stats); __main__ --out va --report bilan
  to'liq ishlaydi.
- Integratsion test (QM-1): demo_shop -> blueprint: user yo'llari 100%, /admin* va /api/admin* faqat
  excluded'da, flows ichida admin yo'li yo'q, topo_order ishlaydi, blueprint sxemadan o'tadi.

Commit: "feat(scanner): classification, flow builder, blueprint and report".
```

**Qabul mezoni:** QM-1 testi yashil. `scan_report.md` ni o'qib, mantiqiyligini o'zingiz tekshiring.

> **F1 oxirida "Faza tekshiruvi" promptini yuboring.**

---

## F2 — Tadqiqotchi (`core.explorer`)

### T09 — Xavfsizlik: url_guard, PolicyEngine, firewall

Rejim: plan

```
@docs/TZ.md (SEC-4, SEC-5, SEC-10) @docs/ARCHITECTURE.md (4.3)
Vazifa: yoriqnoma_core.safety va explorer/firewall.py.

- safety/url_guard.py: check_url(url, *, allow_private: bool) -> URL yoki UrlBlocked xatosi.
  Faqat http/https; host'ning BARCHA DNS natijalari (getaddrinfo) SEC-10 diapazonlariga tekshiriladi;
  IP literal, IPv6, decimal/octal IP yozuvlari ("http://2130706433/") ham ushlanadi.
  allow_private=True faqat lokal dastur uchun (lokal sayt 127.0.0.1 bo'lishi mumkin) — server uni HECH QACHON ishlatmaydi.
- safety/pii.py: email, +998 telefon, karta raqami (Luhn), ism (form label "Ism"/"F.I.Sh" yonidagi qiymat)
  uchun regex/qoidalar; mask_text(); find_pii() (natija tekshiruvi uchun).
- text_uz.py (yoriqnoma_core/text_uz.py): normalize_uz(s) — o'zbek lotin yozuvini bitta ko'rinishga
  keltiradi: kichik harf; apostrof variantlari (' ‘ ’ ` ʻ ʼ) bitta belgiga; yangi alifbo harflari eski
  ko'rinishga: ö -> o', ğ -> g', ş -> sh, ç -> ch. Ba'zi saytlar (masalan, kun.uz) yangi alifboda
  yozilgan: «Öçiriş» = «O'chirish», «Yuboriş» = «Yuborish». Bu funksiya PolicyEngine (T09),
  validate (T15) va HTML qidiruvi (T16) uchun yagona manba.
- safety/policy_engine.py: ARCHITECTURE 4.3 dagi PolicyEngine. allows_click: deny_action_words
  (uz/ru/en; ikkala tomon ham normalize_uz orqali solishtiriladi) — lekin RunContext "own object + staging"
  bo'lsa destructive ruxsat; production'da confirm=True qadamda to'xtash.
- explorer/firewall.py: Playwright context.route("**/*") handler: deny_paths -> abort; boshqa domen:
  resource_type in {stylesheet, script, font, image, media} va GET -> ruxsat, qolgani abort;
  DELETE/PUT/PATCH yo'lidagi id own_objects'da bo'lmasa -> abort. Har abort BlockedRequest sifatida logga.
- Testlar: url_guard uchun 20+ holat (localhost, 127.1, [::1], 169.254.169.254, 10.x, decimal IP,
  ommaviy domen ruxsat); normalize_uz jadval testi (o'chirish, oʻchirish, O‘CHIRISH, öçiriş — bir xil);
  policy jadval testlari, shu jumladan yangi alifboli «Öçiriş» va «Tölaş» tugmalari bloklanadi;
  firewall demo_shop'da: /api/admin so'rovi abort bo'ladi.

Commit: "feat(core): url guard, pii, policy engine, firewall".
```

### T10 — Sessiya, akkauntlar, pochta, test ma'lumoti, qadam bajaruvchi

Rejim: plan

```
@docs/TZ.md (FR-E1..E5) @docs/ARCHITECTURE.md (3.3 Step, 4.3)
Vazifa: explorer/session.py, accounts.py, mailbox.py, datagen.py, steps.py.

- session: Playwright async; har akkaunt (A, B, guest) uchun alohida yangi context
  (viewport, locale uz-UZ, timezone Asia/Tashkent), firewall ulangan.
- datagen: Faker (ru_RU asosida, o'zbekcha ism-familiya ro'yxati qo'shimcha), seed; generatorlar:
  full_name, email (mailbox domeniga: <alias>+<run_id>@<domain>), phone_uz (+998 9X XXX XX XX), password
  (qoidaga mos), text, number(min,max); rules satrini o'qib qiymatni moslash.
- mailbox: MailpitMailbox (REST API: xabarlar ro'yxati, qidiruv to:, xabar matni) va DirMailbox (.eml);
  wait_for(to) -> havola va 6 xonali kodni ajratib beradi.
- accounts: ensure(A, B): berilgan bo'lsa login, bo'lmasa blueprint'dagi register + verify_email
  flow'larini bajarib yaratadi; parollar faqat xotirada; accounts.yaml formati.
- steps: StepExecutor — barcha StepAction'lar; lokator strategiyasi (4.3); "{own:order_id}" ni
  own_objects'dan almashtirish; create'dan keyin URL yoki javobdan yangi obyekt id'sini own_objects'ga yozish;
  human_input HumanInput orqali; har qadam uchun timeout va aniq xato sababi.
- Testlar (slow, demo_shop): ikki akkaunt yaratiladi, email tasdiqlanadi (DirMailbox), login ishlaydi;
  steps birlik testlari (lokator tanlash tartibi).

Commit: "feat(core): sessions, accounts, mailbox, datagen, step executor".
```

### T11 — Runner

```
@docs/TZ.md (FR-E3, FR-E6, FR-E12, SEC-5, SEC-6) @docs/ARCHITECTURE.md (4.3 Runner tartibi)
Vazifa: explorer/runner.py va privilege_check.

- privilege_check (TZ SEC-6): alohida "probe" sahifada — capture o'chirilgan, firewall faqat probe
  GET'lariga ruxsat beradi. (1) blueprint.excluded dagi admin API'larga GET — 401/403/404 kutiladi;
  (2) /admin sahifasini ochib: login'ga qaytarildimi, 403 matnimi yoki admin belgilari (admin, panel,
  users, админ) ko'rindimi. SPA'da status doim 200 bo'lishi mumkinligini hisobga ol — render qilingan
  kontentga qara. Admin ochilsa PrivilegedAccountError — ish to'xtaydi. Faqat ha/yo'q saqlanadi.
- runner: topo_order bo'yicha flow'lar; bog'liqligi failed bo'lgan flow -> skipped (sabab);
  account bo'yicha context tanlash; destructive/payment siyosati; production'da confirm qadamida
  skrinshot olib to'xtash (flow verified, "stopped_at_confirm" belgisi bilan); delete_account eng oxirida.
- Har qadamdan keyin capture hook chaqiriladi (hozircha stub interfeys, T12 da to'ldiriladi).
- progress.json: tugagan flow'lar; qayta ishga tushganda ular o'tkazib yuboriladi (resume).
- Testlar (slow): demo_shop'da to'liq blueprint (T08 natijasi) bilan runner — QM-2: flow'larning ≥ 90%
  verified; capture'da admin sahifasi yoki admin so'rovi 0 (probe natijalari capture'ga yozilmaydi);
  begona buyurtmaga DELETE 0; resume testi; admin akkaunt berilsa PrivilegedAccountError.

Commit: "feat(core): flow runner with dependency order and resume".
```

**Qabul mezoni:** QM-2 testi yashil.

### T12 — Capture: skrinshotlar, elementlar, SoM, maskalash, bundle

Rejim: plan

```
@docs/TZ.md (FR-E9..E11) @docs/ARCHITECTURE.md (3.4, 4.3 Elementlarni yig'ish, 5)
Vazifa: explorer/capture.py, som.py, bundle.py va runner'ga ulash.

- snapshot(page, ctx) -> State: sahifa barqarorligini kutish (networkidle + animatsiyalar tugashi),
  toza skrinshot (full_page=False, viewport), elementlar ro'yxati (JS orqali; ko'rinadigan, interaktiv,
  accessible name), markerlar barqaror tartibda, aria_snapshot, DOM hash (normalizatsiya: raqamlar, vaqt,
  CSRF token'lar olib tashlanadi), network (path templating: raqam/uuid -> :id).
- Maskalash: PII bor input/matn elementlari page.screenshot(mask=[...]) bilan; aria va name'larda mask_text.
- som.py: toza rasmga Pillow bilan raqamli belgilar va ingichka ramka chizish (modelga beriladigan rasm),
  rang kontrasti, belgilar bir-birini yopmasligi.
- capture.json yozish (CaptureRun), images/<state_id>_clean.png va _som.png.
- bundle.py: capture/ -> bundle.zip (faqat json va rasmlar), manifest bilan (sha256 lar).
- Testlar: demo_shop'da register va order sahifalari holatlari; elementlar orasida "Ro'yxatdan o'tish"
  tugmasi bor; email maydoni maskalangan (pii.find_pii skrinshot yonidagi matnlarda bo'sh);
  bundle ochilib sxemadan o'tadi.

Commit: "feat(core): capture, set-of-mark, masking, bundle".
```

### T13 — Holatlar grafi va yamalgan javob

```
@docs/TZ.md (FR-E7, FR-E8) @docs/ARCHITECTURE.md (4.3)
Vazifa: explorer/state_graph.py va patching.py.

- state_graph.explore(page, ctx): xavfsiz nomzodlar — role=tab, aria-expanded elementlar, accordion,
  dropdown/menu, modal ochuvchi (aria-haspopup, data-bs-toggle va h.k.), sahifalash, filtr/saralash;
  har nomzod PolicyEngine.allows_click'dan o'tadi; bosish -> snapshot -> yangi hash bo'lsa saqlash ->
  qaytarish (Escape, yopish tugmasi yoki back); max_depth, max_states; har state'ga parent va trigger
  elementini yoz.
- patching.render_unreachable_statuses(): reachable_by_user=False har status uchun: test user'ning o'z
  obyektini tanlash, uning API javobini route.fetch() bilan olib, faqat status maydonini o'zgartirib
  route.fulfill() qilish; sahifani ochish; snapshot (patched=True). Status maydoni nomi blueprint'dan.
- Testlar (slow): order sahifasida "Tarix" tab holati va bekor qilish modali holati topiladi, modal
  ichidagi "Tasdiqlash" bosilmaydi (explore rejimida); shipped/delivered uchun patched holatlar mavjud.

Commit: "feat(core): state graph exploration and patched status views".
```

> **F2 oxirida "Faza tekshiruvi" promptini yuboring.**

---

## F3 — Yozuvchi va Renderer

### T14 — LLM provayderlari va kesh

Rejim: plan

```
@docs/TZ.md (FR-W1, FR-W3, FR-W7, FR-L6) @docs/ARCHITECTURE.md (4.1)
Vazifa: writer/providers/{base,fake,ollama}.py va writer/cache.py. (ClaudeProvider — T21 da.)

- base: LLMRequest, LLMResult, LLMProvider protokoli, ProviderError, SchemaError.
- fake: deterministik; tests/fixtures/llm/<task>/ dan hash bo'yicha javob, topilmasa sxemadan
  minimal to'g'ri namuna (polyfactory yoki o'zimizniki).
- ollama: ollama.AsyncClient; images fayl yo'llari; format=schema.model_json_schema();
  options={temperature, num_ctx, seed}; keep_alive; timeout; javobni model_validate_json; xato bo'lsa
  xato matnini qo'shib 2 martagacha qayta so'rash; capabilities() — client.show(model) dan
  "vision" borligi; ishga tushishda model yo'q bo'lsa aniq xabar ("ollama pull gemma4:26b").
- cache: fayl asosida (.cache/llm/<sha256>.json), kalit ARCHITECTURE 4.1 dagidek; DB yo'q.
- Testlar: fake bilan unit; cache hit/miss; ollama testi `@pytest.mark.llm` — haqiqiy gemma4:26b'ga
  demo_shop register SoM rasmi bilan kichik sxema so'rovi, javob sxemadan o'tadi.

Commit: "feat(core): llm provider interface, fake and ollama providers, cache".
```

### T15 — Yozuvchi quvuri

Rejim: plan

```
@docs/TZ.md (4.3 to'liq) @docs/ARCHITECTURE.md (3.5)
Vazifa: writer/templates_uz.py, prompts/*.j2, tasks.py, assemble.py, validate.py, coverage.py, pipeline.py.

- templates_uz: har StepAction uchun o'zbekcha gap shablonlari; maydon turi bo'yicha maslahatlar
  ("telefon raqamingizni +998 90 123 45 67 ko'rinishida kiriting", parol qoidalari rules'dan);
  marker raqamini gapga qo'shish ("①"); grammatik to'g'ri qo'shimchalar («Saqlash» tugmasini).
  Tugma va maydon nomi «...» ichida saytdagidek aynan yoziladi, sayt yangi alifboda bo'lsa ham
  («Yuboriş»); atrofdagi matn odatiy lotin yozuvida qoladi.
- prompts: har task uchun versiyalangan Jinja shablon (prompt_version); system prompt: o'zbek tili
  (lotin), qisqa, aniq, "siz" murojaati, faqat rasmda va elementlar ro'yxatida bor narsani yozish,
  admin haqida hech narsa yozmaslik.
- tasks: describe_flow (purpose + notes), describe_statuses (StatusRow'lar), section_intro, faq
  (validatsiya qoidalari va xato xabarlaridan), reference (har sahifa uchun purpose).
  Har biri: kirish -> LLMRequest (SoM rasm + elementlar JSON + flow + qoidalar) -> sxema.
- assemble: 9 bo'lim (TZ FR-W4), stage bo'yicha tartib, failed flow'lar "Tekshirilmagan" ilovasida,
  rasm tanlash (har qadamga mos state). 9 bo'limning hammasi har doim bo'ladi (QM-3). Flow'i yo'q
  bo'lim olib tashlanmaydi: unda shablondan qisqa "Bu saytda bunday imkoniyat topilmadi" matni turadi
  (LLM chaqirilmaydi) va coverage'da sababi yoziladi. Masalan, hisobsiz yangilik saytida 3, 4, 5 va
  7-bo'limlar shunday bo'ladi.
- validate: markerlar mavjud, LLM matnidagi «...» ichidagi nomlar elementlar nomlariga mos
  (fuzzy, T09 dagi normalize_uz bilan: eski va yangi lotin alifbosi, «Yuborish» = «Yuboriş»),
  PII yo'q; xato -> qayta so'rash -> needs_review.
- coverage: TZ FR-W6; percent va items.
- pipeline.write(run_dir, provider) -> manual.json.
- Testlar: FakeProvider bilan demo_shop capture'idan (T12/T13 fixture) to'liq manual; 9 bo'lim;
  QM-3 ning marker va PII qismlari; yangi alifboli elementlar («Yuboriş», «Özbekça») bilan validate
  xato bermaydi; faqat mehmon flow'lari bor capture'da (hisobsiz sayt) ham 9 bo'lim chiqadi,
  bo'sh bo'limlarda "topilmadi" matni va coverage sababi bor; @llm test — gemma4:26b bilan 3 ta flow.

Commit: "feat(core): writer pipeline with uzbek templates, validation, coverage".
```

### T16 — Renderer

Rejim: plan

```
@docs/TZ.md (4.4) @docs/ARCHITECTURE.md (4.4, 5)
Vazifa: render/images.py, html.py, search_index.py, pdf.py, docx.py, templates/.

- images: har StepText uchun yo'riqnoma rasmi — maqsad elementi atrofida qirqim (kontekst bilan),
  spotlight (atrof xiralashadi), raqamli doira belgilar, kerak bo'lsa strelka; patched rasmlarda
  "Namuna ko'rinish" yorlig'i; 2x retina sifat, WebP+PNG.
- html: Jinja2; chap tomonda mundarija (bo'limlar -> maqolalar), qadamlar raqamlangan, rasmlar lazy,
  statuslar jadvali, FAQ, A–Z ma'lumotnoma; search_index.json + kichik vanilla JS qidiruv (offline;
  T09 dagi normalize_uz jadvalining JS nusxasi: apostrof variantlari va ö/ğ/ş/ç, ya'ni "yuborish"
  so'rovi «Yuboriş» ni topadi); toza, o'qishli tipografiya; chop etish uchun print CSS.
- pdf: Playwright page.pdf(A4, sahifa raqamlari, sarlavha/pastki qism) — HTML'dan.
- docx: python-docx — Heading 1/2/3, raqamlangan qadamlar, rasmlar (kenglik 15 sm) va izohlari,
  TOC maydoni, jadval uslubi.
- coverage_report.html.
- Testlar: FakeProvider manual'idan dist/ yaratiladi; HTML'da barcha bo'limlar; PDF > 0 sahifa;
  DOCX ochiladi va sarlavhalar soni to'g'ri; rasmlar mavjud; normalize_uz jadval testi Playwright'da
  JS nusxasiga ham beriladi va Python bilan bir xil natija chiqadi.

Commit: "feat(core): renderer html, pdf, docx with annotated images".
```

**Qabul mezoni:** `dist/html/index.html`, PDF va DOCX'ni o'zingiz ochib ko'ring. Ko'rinishi va o'qilishi bo'yicha fikringizni keyingi sessiyada yozing.

### T17 — `core.pipeline`: dasturlar uchun umumiy kirish nuqtasi

```
@docs/ARCHITECTURE.md (5-bo'lim, 4.3, 4.1)
Vazifa: packages/core/src/yoriqnoma_core/pipeline.py — ikkala Django dasturi chaqiradigan yagona API.

- Protokollar: ProgressSink (stage(name, total), advance(n=1), log(level, msg), event(kind, payload)),
  CancelToken (is_cancelled() -> bool; har flow/holat/LLM chaqiruvi orasida tekshiriladi ->
  Cancelled xatosi), HumanInput (ARCHITECTURE 4.3).
- async run_explore(blueprint, run_dir, opts, human, progress, cancel) -> CaptureRun;
  async run_write(run_dir, provider, progress, cancel) -> Manual; run_render(run_dir, formats) -> RenderResult;
  make_bundle(run_dir) -> Path.
- ExploreOptions (pydantic): base_url, environment, accounts (A/B login+parol, ixtiyoriy), mailbox,
  allow_private (default False!), headless, viewport, locale, seed, limits.
- Oddiy implementatsiyalar testlar va debug uchun: ConsoleProgressSink, NeverCancel, TerminalHumanInput.
- `python -m yoriqnoma_core run --blueprint B --base-url URL --out DIR --provider fake|ollama` — debug.
- Testlar (slow): demo_shop'da FakeProvider bilan run_explore -> run_write -> run_render to'liq zanjir;
  cancel testi (ikkinchi flow'da bekor qilish -> progress.json saqlanadi, resume ishlaydi).

Commit: "feat(core): pipeline api for applications".
```

**Qabul mezoni:** `python -m yoriqnoma_core run ... --provider fake` demo_shop uchun `dist/` yaratadi.

> **F3 oxirida "Faza tekshiruvi" promptini yuboring.**

---

## F4 — Lokal dastur (`apps/local`, Django)

### T18 — Lokal dastur: modellar, servislar, Huey, launcher, buyruqlar

Rejim: plan

```
@CLAUDE.md @docs/TZ.md (3, 4.5, SEC-16) @docs/ARCHITECTURE.md (6, 8)
Vazifa: apps/local ning backend qismi (UI keyingi vazifada).

- Modellar (ARCHITECTURE 6.2): AppSettings (singleton), Project, ProjectAccount, BlueprintVersion,
  Run, RunEvent, InputRequest; migratsiyalar; Fernet shifrlash yordamchisi (var/secret.key birinchi
  ishga tushishda yaratiladi) — parollar shifrlangan.
- services.py (biznes mantiq faqat shu yerda):
  scan_project(project) -> BlueprintVersion (scanner.scan, fayllar var/runs/... ga);
  upload_blueprint(project, file) -> BlueprintVersion (sxema tekshiruvi);
  set_override(bv, kind, key, value) — scanner.overrides qoidalari bo'yicha;
  start_run(project, output, model, formats) -> Run; execute_run(run_id) — ARCHITECTURE 6.3 dagi
  3 natija turi; cancel_run; answer_input.
- DbProgressSink, DbCancelToken, DbHumanInput (core.pipeline protokollari).
- Huey vazifalari: scan_project_task, execute_run_task (Playwright -> asyncio.run ichida).
  Bir vaqtda faqat 1 ta explore (Huey lock) — GPU va brauzer uchun.
- OllamaProvider AppSettings'dan; allow_private=True (lokal saytlar uchun), lekin base_url
  http(s) va ochiladigan bo'lishi tekshiriladi.
- health.py: Ollama (ishlayaptimi, model bormi, vision), Playwright chromium, base URL — o'zbekcha xabarlar.
- launcher.py (yoriqnoma-local): migrate -> health -> waitress 127.0.0.1:8765 (thread) + huey consumer
  (subprocess: manage.py run_huey -w 2 -k thread) -> brauzerni ochish -> Ctrl+C ikkalasini to'xtatadi.
- Boshqaruv buyruqlari (ARCHITECTURE 6.5): scan, explore, write, render, run, bundle — services'ni chaqiradi,
  terminalda progress va input().
- Testlar: services unit (huey immediate=True, FakeProvider); slow — demo_shop'da run --output full|bundle|blueprint
  uchala natija turi; blueprint natijasi sxemadan o'tadi; bundle ochilib capture sxemadan o'tadi;
  overrides excluded'ni qaytara olmasligi testi.

Commit: "feat(local): models, services, huey tasks, launcher, management commands".
```

**Qabul mezoni:**

```
uv run python apps/local/manage.py run --project demo --output full
```

Bu buyruq demo_shop uchun `dist/` (HTML, PDF, DOCX) yaratadi. Avval `scan --path fixtures/demo_shop --base-url http://127.0.0.1:8800` bilan loyiha yarating.

### T19 — Lokal dastur: veb-interfeys

Rejim: plan

```
@docs/TZ.md (4.5 FR-L3..L9) @docs/ARCHITECTURE.md (6.3, 6.4)
Vazifa: apps/local veb-interfeysi — Django shablonlar + HTMX, o'zbek tilida, toza va sodda dizayn
(bitta CSS fayl, tashqi CDN'larsiz — offline ishlashi kerak; htmx.min.js static ichida).

- Sahifalar ARCHITECTURE 6.4 jadvalidagidek. Asosiy talablar:
  * Bosh sahifa: loyihalar kartalari + tizim holati paneli (Ollama/model/Playwright — yashil/qizil, yechim matni).
  * Loyiha formasi: kod papkasi yo'li (matn maydoni + "tekshirish": mavjudmi, stek nima — detect natijasi),
    base URL, muhit (production tanlansa ogohlantirish), A/B akkauntlar (ixtiyoriy), pochta.
  * Blueprint ko'rib chiqish: tablar (Sahifalar, Obyektlar va statuslar, Flow'lar bosqichlar bo'yicha,
    Chiqarib tashlanganlar — sabab bilan, Skan hisoboti); har sahifa/flow yonida "Chiqarish" toggle
    (HTMX POST -> set_override), flow nomini tahrirlash; statistika.
  * Yangi ish: 3 ta katta radio karta — "To'liq yo'riqnoma (lokal, Ollama)", "Blueprint (server A uchun)",
    "Bundle (server A' uchun)" — har birida qisqa tushuntirish, taxminiy vaqt; model va formatlar faqat
    "To'liq" uchun ko'rinadi.
  * Ish sahifasi: bosqichlar chizig'i, progress bar, jonli log (HTMX har 2 s), InputRequest bo'lsa
    sariq panel va kod kiritish formasi, "Bekor qilish", tugagach natijalar: "Yo'riqnomani ochish"
    (dist/html/index.html — /runs/<id>/files/ orqali), PDF/DOCX/blueprint/bundle/hisobot yuklab olish,
    "Papkani ochish"; blueprint va bundle yonida "Bu faylni server sahifasidagi «Yangi ish» formasida
    yuklang" ko'rsatmasi (lokal dastur serverga ulanmaydi).
  * Sozlamalar: Ollama host, o'rnatilgan modellar ro'yxati (Ollama /api/tags) dan tanlash, "Ulanishni
    tekshirish".
- Fayl berish: faqat run_dir ichidagi fayllar (resolve + is_relative_to tekshiruvi).
- Testlar: Django test client — barcha sahifalar 200, formalar validatsiyasi, override toggle,
  path traversal rad etiladi, CSRF yoqilgan.

Commit: "feat(local): htmx web ui".
```

**Qabul mezoni:** `uv run yoriqnoma-local` ni ishga tushiring. Brauzerda quyidagi zanjirni boshidan oxirigacha o'tkazing: demo_shop loyihasini yaratish → skanerlash → ko'rib chiqish → "To'liq yo'riqnoma" → natijani ochish. Interfeys bo'yicha fikrlaringizni yozib qo'ying.

### T20 — Modellarni solishtirish (`eval`)

```
@docs/TZ.md (FR-L12) @docs/ARCHITECTURE.md (9 Oltin to'plam)
Vazifa: apps/local/evaluation ilovasi va tests/golden/.

- tests/golden/: demo_shop capture'idan 25 ta holat (turli sahifalar, modal, forma, status) + har biri
  uchun expected.json (sahifa vazifasida bo'lishi kerak kalit so'zlar, eslatilishi kerak markerlar,
  eslatilmasligi kerak narsalar).
- services.run_eval(models) (Huey vazifasi) va manage.py eval: har model uchun describe_flow/describe_statuses;
  metrikalar: sxema xatosi, marker xatosi, kalit so'zlar qamrovi, taqiqlangan so'zlar, o'rtacha vaqt.
- /eval/ sahifasi: modellar tanlash (Ollama ro'yxatidan), natijalar jadvali, yonma-yon matnlar,
  har biriga 1–5 baho (bazaga saqlanadi), "Asosiy model qilib belgilash" tugmasi (AppSettings).
- @llm test: gemma4:26b va qwen3.6:27b bilan.

Commit: "feat(local): model evaluation".
```

**Qabul mezoni:** `/eval/` da ikki modelni solishtiring va asosiy modelni tanlang.

> **F4 oxirida "Faza tekshiruvi" promptini yuboring.** Shu bosqichda lokal dastur to'liq ishlaydigan holatga keladi.

---

## F5 — Server dastur (`apps/server`, Django): A va A' rejimlari

### T21 — ClaudeProvider

Rejim: plan

```
@docs/TZ.md (FR-SV6, SEC-7) @docs/ARCHITECTURE.md (4.1, 8)
Vazifa: packages/core/.../writer/providers/claude.py (Django'siz).

- anthropic.AsyncAnthropic; messages.parse(model, max_tokens, system=[{type:"text", text,
  cache_control:{type:"ephemeral"}}], messages=[rasm bloklari (base64 PNG) + matn], output_format=schema)
  -> response.parsed_output. (Hujjat: https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Model tanlash konstruktor parametridan: task -> model (classify -> haiku, describe_* -> sonnet,
  final_review -> opus).
- usage'dan token va narx hisobi (narxlar parametr sifatida), cache_read/creation tokenlari alohida;
  BudgetExceeded — byudjetdan oshsa (ProgressSink.event("cost", ...) orqali xabar).
- Rate limit va 5xx uchun exponential backoff; SchemaError bo'lsa 2 martagacha qayta urinish.
- Yuborishdan oldin: rasm maskalangan ekanini tekshirish (capture metadata), matnlarda pii.mask_text.
- Kalit (TZ SEC-12): AsyncAnthropic(api_key=...) ga konstruktor orqali beriladi; provider Django
  sozlamalarini o'qimaydi. Kalit provider'ning repr/str, log yozuvlari va xato matnlariga hech qachon
  tushmaydi (test: soxta "sk-ant-test-..." kalit bilan xato chiqarib, matnda kalit yo'qligini tekshirish).
- writer pipeline'ga final_review bosqichi (faqat provider "final_review" ni qo'llasa): Opus butun manual +
  har bo'limdan 1-2 rasm bilan izchillik va xatolarni tekshiradi, tuzatishlar ro'yxatini qaytaradi, ular qo'llaniladi.
- Testlar: mock client bilan unit (so'rov tuzilishi, cache_control, budget); @llm haqiqiy API bilan
  kichik so'rov (ANTHROPIC_API_KEY bo'lsa).

Commit: "feat(core): claude provider with structured outputs, caching, budget".
```

### T22 — Server skeleti: modellar, Celery, API, Docker

Rejim: plan

```
@docs/TZ.md (4.6) @docs/ARCHITECTURE.md (7.1–7.5, 8)
Vazifa: apps/server backend skeleti va docker/.

- Modellar (ARCHITECTURE 7.2): domains.Domain, jobs.Job/JobEvent/InputRequest/Artifact;
  Argon2PasswordHasher birinchi; Django admin /ops/ (staff).
- DRF: faqat SessionAuthentication (API kalitlar yo'q); IsOwner permission; ARCHITECTURE 7.4 dagi barcha endpointlar (ish hozircha
  "dummy pipeline" bilan: bosqichlarni o'tib, soxta artifact yaratadi).
- Celery: celery.py, jobs.tasks.run_job (state machine 7.3, JobProgressSink/JobCancelToken/JobHumanInput),
  cleanup_expired va reap_stuck_jobs (beat), time_limit, acks_late, prefetch 1.
- Storage: django-storages S3 (MinIO), Artifact yuklab olish — qisqa muddatli presigned URL'ga redirect.
- docker/: Dockerfile.web (gunicorn), Dockerfile.worker (Playwright rasmiy Python image asosida,
  root'siz user), compose.yml — caddy, web, worker, beat, postgres, redis, minio, mailpit; profil "test" da
  demo_shop; healthcheck'lar. Env fayllar (ARCHITECTURE 8): docker/.env — hamma servislar uchun, Claude
  kalitisiz; docker/worker.env — faqat ANTHROPIC_API_KEY, faqat worker servisiga env_file bilan.
  Repoda qiymatsiz .env.example va worker.env.example. Kalit Dockerfile'ga (ARG/ENV) yozilmaydi.
- Worker ishga tushganda (Celery worker_init signali) ANTHROPIC_API_KEY bo'sh bo'lsa, aniq xabar bilan
  to'xtaydi (TZ SEC-12).
- Xarajat limitlari (TZ FR-SV6): ish yaratishda (veb va API) foydalanuvchining shu kungi va shu oydagi
  sarfi hamda serverning shu oydagi sarfi tekshiriladi (Job.cost_usd yig'indisi + yangi ishning
  budget_usd). Limitdan oshsa ish yaratilmaydi va o'zbekcha sababi ko'rsatiladi. Limitlar env'dan
  (YORIQNOMA_USER_DAILY_BUDGET_USD, YORIQNOMA_USER_MONTHLY_BUDGET_USD, YORIQNOMA_MONTHLY_BUDGET_USD).
- Testlar (pytest-django, CELERY_TASK_ALWAYS_EAGER): boshqa user ishini
  ko'ra olmaslik (SEC-15), job yaratish -> hodisalar ketma-ketligi, bekor qilish; xarajat limitlari
  (kunlik, oylik, server bo'yicha — oshganda ish yaratilmaydi); worker kalitsiz ishga tushmaydi;
  compose konfiguratsiyasida ANTHROPIC_API_KEY faqat worker servisida; `server` marker — compose'da smoke.

Commit: "feat(server): models, drf api, celery, storage, docker compose".
```

### T23 — Server xavfsizligi

Rejim: plan

```
@docs/TZ.md (SEC-9..SEC-17) @docs/ARCHITECTURE.md (7)
Vazifa: apps/server/security va domains integratsiyasi.

- domains/services.verify(domain): token; usullar — https://<host>/.well-known/yoriqnoma-verify.txt,
  <meta name="yoriqnoma-verify" content=token>, DNS TXT (dnspython) "yoriqnoma-verify=<token>";
  barcha so'rovlar url_guard (allow_private=False) orqali; natija Domain'ga.
- Passiv rejim: tasdiqlanmagan domen uchun Job.passive=True va Policy override — register/login/forma
  yuborish/agent fill/click(submit) taqiqlanadi, faqat guest sahifalar; UI'da aniq ogohlantirish.
- SSRF: job yaratishda url_guard (serializer validatsiyasi); worker'da Playwright route handler har yangi
  host uchun url_guard; redirect'lar; httpx uchun maxsus transport. Worker konteyneri egress qoidalari
  (docker network + iptables yoki egress proxy — oddiyrog'ini tanla, docs/DEPLOY.md da tushuntir).
- secrets: Fernet (YORIQNOMA_FERNET_KEY) — Job.accounts_enc, InputRequest.value_enc; ish tugagach
  o'chirish; logging filter (parol, token, cookie, Authorization, x-api-key sarlavhasi va
  "sk-ant-" bilan boshlanadigan har qanday qiymat maskalanadi; Django, Celery va anthropic loggerlariga ulanadi).
- ratelimit: domen bo'yicha token bucket (Redis); robots.py (urllib.robotparser); User-Agent sozlamadan.
- Django hardening (SEC-17): prod settings — SECURE_HSTS_*, SECURE_SSL_REDIRECT, SESSION/CSRF_COOKIE_SECURE,
  django-csp, login urinishlarini cheklash (django-axes); `manage.py check --deploy` toza.
- Testlar (QM-5 qismi): 127.0.0.1, localhost, 169.254.169.254, [::1], 0x7f000001, ichki IP'ga redirect
  qiladigan tashqi URL (mock), DNS ikki xil javob (rebinding simulyatsiyasi) — hammasi bloklanadi;
  tasdiqlanmagan domenda forma yuborilmaydi; loglarda parol va Claude kaliti yo'q (soxta
  "sk-ant-test-..." kalit va x-api-key sarlavhasi log qilinganda maskalanadi).

Commit: "feat(server): domain verification, ssrf protection, secrets, hardening".
```

### T24 — A va A' rejimlari hamda server veb-interfeysi

Rejim: plan

```
@docs/TZ.md (FR-SV1..SV3, SEC-13) @docs/ARCHITECTURE.md (7.3–7.5)
Vazifa: jobs/services.py ichida haqiqiy pipeline (A, A') va server veb-interfeysi.

- A: blueprint yuklash (sxema tekshiruvi, base_url host'i tasdiqlangan Domain bilan mos) ->
  core.pipeline.run_explore (allow_private=False, firewall, ratelimit) -> run_write(ClaudeProvider,
  budget) -> run_render -> Artifact'lar MinIO'ga.
- A': bundle.zip — hajm limiti, zip slip (har yo'l normalizatsiya, root'dan chiqmasin), faqat ruxsat
  etilgan kengaytmalar, manifest sha256 tekshiruvi, capture sxemasi; keyin run_write -> run_render.
- Veb sahifalar (Django shablonlar + HTMX, o'zbek tilida; lokal dastur bilan bir xil uslub):
  login/register, /domains/ (qo'shish,
  3 usul bo'yicha joylash yo'riqnomasi, "Tekshirish"), /jobs/new/ (rejim kartalari: A, A', B (hozircha
  "tez orada"), URL, muhit, akkauntlar, fayl yuklash, byudjet), /jobs/<id>/ (bosqichlar, log — events
  polling har 2 s, narx, input formasi, bekor qilish, natijalar), /jobs/.
- Testlar (server): compose'da demo_shop'ga A rejimi (blueprint T08'dan) va A' (bundle T18'dan) —
  natijada HTML/PDF/DOCX artifact'lari; zip slip va katta fayl rad etiladi.

Commit: "feat(server): modes A and A-prime with web ui".
```

**Qabul mezoni:** server UI orqali demo_shop uchun A rejimida ish yarating va yo'riqnomani yuklab oling.

### T25 — Lokal natijani serverga qo'lda olib o'tish

```
@docs/TZ.md (FR-L9, FR-SV9, SEC-13) @docs/ARCHITECTURE.md (6.3 5-qadam, 7.5)
Vazifa: lokal va server o'rtasida avtomatik aloqa YO'Q — fayl odam orqali o'tadi. Shu yo'lni qulay va xavfsiz qil.

- Lokal (local/): ish sahifasida blueprint.json / bundle.zip ni yuklab olish tugmasi, faylning hajmi va sha256,
  qisqa ko'rsatma: "Bu faylni server sahifasidagi «Yangi ish» formasida yuklang".
- Server (server/): /jobs/new/ dagi fayl maydoni — fayl turi tanlangan rejimga (A yoki A') mosligi tekshiriladi;
  sxemaga mos kelmagan, zip slip yoki juda katta fayl uchun aniq o'zbekcha xabar; ish source="web".
- Ajratish testi (local/tests): lokal kodda server API'siga murojaat yo'q (/api/jobs kabi yo'llar, server URL
  yoki kalit sozlamalari topilmaydi); lokal sozlamalarda server manzili maydoni yo'q.
- Testlar (server/tests): lokal dastur chiqaradigan formatdagi namunaviy blueprint.json va bundle.zip
  (docs/schemas/examples va T18 namunasi) /jobs/new/ orqali yuklanadi -> ish yaratiladi (QM-4);
  buzilgan fayllar rad etiladi.

Commit: "feat: manual hand-off of local results to the server".
```

> **F5 oxirida "Faza tekshiruvi" promptini yuboring.**

---

## F6 — Server: B rejimi (mustaqil, faqat URL)

### T26 — Razvedkachi, 1-qism: kodsiz kashfiyot

Rejim: plan

```
@docs/TZ.md (FR-SV5) @docs/ARCHITECTURE.md (7.6)
Vazifa: apps/server/scout — preflight.py, crawler.py, js_routes.py, network_infer.py
(mantiq toza Python modullarda, Django faqat Job/ProgressSink orqali).

- preflight: url_guard, domen tasdiqlanganmi (aks holda passiv), robots.txt, sitemap.xml (index ham),
  html lang, texnologiya belgilari (meta generator, skript nomlari).
- crawler: guest context'da BFS (faqat shu origin), URL shablonlash (/x/123 -> /x/:id, uuid, slug
  heuristikasi), har shablondan ≤ 2 namuna, deny_paths, robots, ratelimit, max_pages; har sahifada
  capture.snapshot (keyingi bosqichlar uchun).
- js_routes: sahifa yuklagan, shu origin'ga tegishli JS fayllardan tree-sitter/regex bilan route satrlari
  (path:"/...", <Route path=...>, router config'lar), ochiq *.map bo'lsa sourcesContent'dan; topilgan
  yo'llar crawler navbatiga (deny_paths filtri bilan).
- network_infer: ko'rilgan XHR/fetch (metod + shablon) -> entity va action nomzodlari
  (REST naqshlari, /api/<resurs>/:id/<fe'l>), confidence.
- Natija: qisman Blueprint (source="discovered") — pages, nav, forms (DOM'dan), entities.
- Testlar (server): demo_shop'da kodsiz: barcha guest sahifalar, JS'dan /app/* yo'llari topiladi,
  /admin* excluded'da.

Commit: "feat(scout): preflight, crawler, js routes, network inference".
```

### T27 — Razvedkachi, 2-qism: kirish, agent, birlashtirish

Rejim: plan

```
@docs/TZ.md (FR-SV5, SEC-6, SEC-8) @docs/ARCHITECTURE.md (7.6)
Vazifa: scout/auth_flow.py, agent.py, validation_probe.py, blueprint_builder.py, merge.py va
jobs pipeline'ga B va A+B rejimlari.

- auth_flow: register/login sahifalarini topish (Haiku tasnifi: sahifa turi), formani to'ldirish
  (datagen), test pochta job-<id>@inbox.<domen> (server Mailpit), tasdiqlash; captcha topilsa
  JobHumanInput yoki "tayyor akkaunt bering" xabari bilan to'xtash. Keyin core privilege tekshiruvi.
- agent: Claude Sonnet tool use sikli. Har qadamda: SoM rasm + elementlar + hozirgi flow konteksti +
  topilgan flow'lar ro'yxati. Tool'lar ARCHITECTURE 7.6 dagidek; har chaqiruv PolicyEngine'dan;
  natija agentga qaytadi; byudjet (sahifa, qadam, $) tugasa to'xtaydi. Maqsad: har sahifadagi user
  vazifalarini topish va bajarib, Flow sifatida yozish (steps — haqiqatda bajarilgan qadamlar).
- validation_probe: o'z obyekti formalarida bo'sh/noto'g'ri qiymat bilan submit, xato xabarlarini
  yig'ish -> Form.rules va FAQ manbasi.
- blueprint_builder: discovered blueprint, confidence; merge: A+B — kod ustun, discovered yangi
  narsalarni qo'shadi, ziddiyatlar hisobotga.
- Keyin standart quvur (run_explore -> run_write -> run_render), manual.source_mode = "B" yoki "A+B";
  coverage hisobotida "faqat sayt orqali topilgan" ogohlantirishi. /jobs/new/ da B kartasi faollashadi.
- Testlar (server): demo_shop'ga B rejimi — QM-6: qamrov A rejimiga nisbatan ≥ 70%; admin yo'q;
  begona buyurtmalar ko'rinmaydi; byudjet limiti ishlaydi.

Commit: "feat(scout): auth, claude agent, validation probe, merge; mode B".
```

### T28 — Server e2e, mustahkamlash va deploy

```
@docs/TZ.md (9-bo'lim QM-4..QM-6, NFR-4)
Vazifa: tests/e2e/server/ — compose'da A, A', B va A+B rejimlarini to'liq o'tkazuvchi testlar,
lokal dastur fayllarini server formasida qo'lda yuklash zanjiri, vaqt o'lchovlari (NFR-4 bilan solishtirish), narx hisoboti,
xatolik stsenariylari (sayt o'chib qolsa, Claude xatosi, byudjet tugashi, bekor qilish).
docs/DEPLOY.md: serverga o'rnatish (domen, Caddy TLS, MX yozuvi test pochta uchun, env'lar,
superuser yaratish, zaxira nusxa — Postgres va MinIO, yangilash tartibi, monitoring).
Claude kaliti bo'limi: kalitni docker/worker.env ga qo'yish (fayl huquqi 600, faqat server egasi o'qiydi);
almashtirish tartibi — yangi kalitni yozib worker'ni qayta ishga tushirish, keyin eskisini Anthropic
Console'da o'chirish; Console'da oylik sarf limitini qo'yish (FR-SV6 limitlariga qo'shimcha himoya);
kalit chiqib ketsa nima qilish.
Topilgan kamchiliklarni tuzat.
Commit: "test(server): e2e for all modes; docs: deploy guide".
```

> **F6 oxirida "Faza tekshiruvi" promptini yuboring.**

---

## F7 — Kengaytirish (kerak bo'lganda)

### T29 — Skanerga yangi stek qo'shish (har stek uchun alohida sessiya)

Tavsiya: birinchi bo'lib **Django** stekini qo'shing, chunki o'z loyihalaringiz shu stekda bo'lishi mumkin.

```
@docs/ARCHITECTURE.md (4.2) @packages/scanner/src/yoriqnoma_scanner/parsers/fastapi_routes.py (namuna)
Vazifa: Skanerga <STEK> qo'llab-quvvatlashini qo'sh (Django | Flask | Laravel | Vue Router |
Next.js app/pages | Express).
- detect.py ga aniqlash; parsers/<stek>.py — route'lar, guard'lar (admin rol tekshiruvlari -> role,
  egalik -> ownership), formalar/validatsiya, modellar (ORM bo'lsa — faqat AST, hech qanday import yo'q).
  Django uchun: urls.py (path/re_path/include zanjiri), view dekoratorlari va mixin'lar
  (login_required -> auth; staff_member_required, user_passes_test(is_staff), PermissionRequiredMixin,
  UserPassesTestMixin -> role; get_queryset ichida filter(user=request.user) -> ownership),
  forms.py/ModelForm va DRF serializer validatsiyalari, models.py (ForeignKey(User) -> owner, choices -> statuslar),
  templates (form maydonlari, {% trans %} matnlari), locale/*.po.
- tests/fixtures/snippets/<stek>/ namunalar va testlar; kichik namunaviy loyiha (Django uchun —
  fixtures/demo_django: 5–6 sahifa, admin va user qismlari) — classify va blueprint integratsion testi
  (admin excluded, user sahifalar topilgan).
Commit: "feat(scanner): <stek> support".
```

### T30 — Inkremental yangilash, CI va interaktiv tur

```
@docs/TZ.md (8-bo'lim) @docs/ARCHITECTURE.md
Vazifa:
- Inkremental rejim: yangi capture'ni oldingi run bilan holat hash bo'yicha solishtirish; faqat
  o'zgargan holatlarga tegishli maqolalarni qayta yozish; o'zgarishlar ro'yxati (changelog.md).
  Lokal dasturda "Oldingi natija asosida yangilash" tugmasi.
- docs/ci/github-action.yml namunasi: deploy'dan keyin staging'ga lokal dasturning `manage.py run`
  buyrug'i yoki server API (A rejimi) orqali yo'riqnomani yangilab, artifact sifatida saqlash.
- Driver.js uchun tur eksporti (har flow -> steps JSON: selector + o'zbekcha matn) va GIF eksporti
  (har flow skrinshotlaridan).
Commit: "feat: incremental regeneration, ci example, tour and gif export".
```
