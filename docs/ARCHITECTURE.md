# Arxitektura: AI_user_yoriqnoma

Talablar: `docs/TZ.md`. Bu hujjatda kod darajasidagi tuzilma, sxemalar va interfeyslar berilgan. Tizim ikki Django dasturi (Lokal va Server) va uchta umumiy Python paketidan iborat.

## 1. Repo tuzilmasi

Repo ikki **mustaqil** dasturga bo'lingan. Har biri o'z papkasida, o'z `pyproject.toml`, `uv.lock` va `.venv` bilan alohida uv workspace:
- **`local/`** — lokal dastur (Django). Foydalanuvchi kompyuterida ishlaydi.
- **`server/`** — server dastur (Django). Onlayn serverda, Docker'da ishlaydi.

Kutubxona paketlari toza Python, Django'ga bog'liq emas. Ikkala dasturga kerak bo'lgan `schemas` va `core` har bir dastur ichida **aynan bir xil nusxa** sifatida turadi (`local/packages/`, `server/packages/`). Shunda har bir dastur boshqasisiz o'rnatiladi va o'z mashinasiga ko'chiriladi. Nusxalar bir xilligini ikkala dasturdagi `tests/test_shared_copies.py` tekshiradi: birini o'zgartirsangiz, papkani ikkinchisiga ham ko'chiring.

```
ai-user-yoriqnoma/
├── CLAUDE.md  README.md  .gitignore  .gitattributes  .pre-commit-config.yaml
├── .github/workflows/ci.yml       # alohida job'lar: local (ubuntu + windows), server (ubuntu)
├── docs/                          # TZ.md, ARCHITECTURE.md, TASKS.md, schemas/*.json
├── local/                         # LOKAL DASTUR — §6
│   ├── pyproject.toml  uv.lock  .python-version   # yoriqnoma-local + workspace (packages/*)
│   ├── manage.py  startup.bat     # startup.bat — Windows'da bir bosishda ishga tushirish
│   ├── yoriqnoma_local/           # settings.py, settings_test.py, urls.py, huey.py, launcher.py (yoriqnoma-local)
│   ├── projects/                  # Project, ProjectAccount; scan + blueprint ko'rib chiqish
│   ├── runs/                      # Run, RunEvent, InputRequest; services.py; tasks.py (huey)
│   ├── settings_app/              # AppSettings (Ollama)
│   ├── evaluation/                # model solishtirish
│   ├── templates/  static/        # HTMX (htmx.min.js lokal nusxa, CDN yo'q)
│   ├── */management/commands/     # scan, explore, write, render, run, bundle, eval
│   ├── packages/
│   │   ├── schemas/src/yoriqnoma_schemas/
│   │   │   ├── common.py          # Target, BBox, Role, Stage, Confidence...
│   │   │   ├── policy.py          # Policy
│   │   │   ├── blueprint.py       # Blueprint, Page, Entity, Flow, Step
│   │   │   ├── capture.py         # CaptureRun, State, Element, FlowResult
│   │   │   ├── manual.py          # Manual, Section, Article, Coverage
│   │   │   └── export.py          # JSON Schema → docs/schemas/
│   │   ├── scanner/src/yoriqnoma_scanner/   # FAQAT LOKALDA
│   │   │   ├── api.py             # scan(project_dir, base_url, stack="auto") -> ScanResult
│   │   │   ├── __main__.py        # debug: python -m yoriqnoma_scanner PATH --base-url URL
│   │   │   ├── fs_guard.py  detect.py  ast_utils.py
│   │   │   ├── parsers/           # base.py, fastapi_routes.py, react_router.py,
│   │   │   │                      # jsx_forms.py, pydantic_forms.py, zod_yup.py,
│   │   │   │                      # sqlalchemy_models.py, i18n.py,
│   │   │   │                      # e2e_playwright_py.py, e2e_playwright_ts.py
│   │   │   └── classify.py  entities.py  flows.py  build.py  report.py  overrides.py
│   │   └── core/src/yoriqnoma_core/
│   │       ├── safety/            # url_guard.py, pii.py, policy_engine.py
│   │       ├── explorer/          # session, accounts, firewall, datagen, mailbox,
│   │       │                      # steps, runner, capture, som, state_graph,
│   │       │                      # patching, zones, pseudonymize, ocr, bundle, privilege
│   │       ├── writer/            # providers/{base,fake,ollama,claude}.py,
│   │       │                      # templates_uz.py, prompts/*.j2, tasks.py,
│   │       │                      # assemble.py, validate.py, coverage.py, cache.py
│   │       ├── render/            # images.py, html.py, pdf.py, docx.py,
│   │       │                      # search_index.py, templates/
│   │       └── pipeline.py        # run_explore(), run_write(), run_render() — dasturlar chaqiradi
│   ├── fixtures/demo_shop/        # poligon (§10)
│   ├── tests/                     # test_no_db_drivers.py, test_shared_copies.py, golden/
│   └── var/                       # o'z ma'lumotlari: local.sqlite3, huey.sqlite3, kalitlar, runs/ (git'da yo'q)
└── server/                        # SERVER DASTUR — §7
    ├── pyproject.toml  uv.lock  .python-version   # yoriqnoma-server + workspace (packages/*)
    ├── manage.py
    ├── yoriqnoma_server/          # settings/{base,dev,prod,test}.py, urls.py, celery.py, asgi/wsgi
    ├── accounts/                  # Django auth: ro'yxatdan o'tish va kirish
    ├── domains/                   # Domain, domen tasdiqlash
    ├── jobs/                      # Job, JobEvent, Artifact, InputRequest; services; tasks (celery)
    ├── scout/                     # B rejimi: preflight, crawler, js_routes, network_infer,
    │                              # auth_flow, agent, validation_probe, blueprint_builder, merge
    ├── security/                  # ssrf integratsiyasi, secrets (Fernet), ratelimit, robots
    ├── api/                       # DRF: serializers, views, permissions, urls (faqat sessiya)
    ├── storage.py                 # django-storages S3 (MinIO)
    ├── templates/  static/        # HTMX
    ├── packages/
    │   ├── schemas/               # local/packages/schemas ning aynan nusxasi
    │   └── core/                  # local/packages/core ning aynan nusxasi
    ├── docker/                    # Dockerfile.web, Dockerfile.worker, compose.yml,
    │                              # .env.example, worker.env.example (haqiqiy env'lar git'da yo'q)
    ├── tests/                     # test_no_db_drivers.py, test_shared_copies.py, e2e/
    └── var/                       # dev ma'lumotlari (git'da yo'q)
```

**Bog'liqliklar:**

| Qism | Nimaga bog'liq |
|---|---|
| `schemas` | Hech narsaga (faqat pydantic) |
| `scanner` | Faqat `schemas` |
| `core` | Faqat `schemas` |
| `local/` dasturi | o'zidagi `schemas`, `scanner`, `core` + Django, Huey, waitress |
| `server/` dasturi | o'zidagi `schemas`, `core` + Django, DRF, Celery, psycopg, django-storages |

**Muhim:**
- `server/` da `scanner` yo'q. Server kod o'qimaydi: blueprint'ni foydalanuvchi yuklagan fayldan oladi yoki saytning o'zidan tuzadi.
- Lokal va server bir-biriga ulanmaydi va bir-birining papkasidan import qilmaydi. Lokal natijasi (`blueprint.json`, `bundle.zip`) serverga faqat odam orqali o'tadi.

## 2. Ma'lumot oqimi

```
 ┌──────────────────────── LOKAL DASTUR (local/, Django, 127.0.0.1) ──────────────────────────┐
 │  kod ─► scanner.scan() ─► blueprint ─► [ko'rib chiqish, overrides] ─┬─► blueprint.json      │
 │                                                                     │                       │
 │                     core.explorer (Playwright) ◄────────────────────┘                       │
 │                            │                                                                │
 │                 capture/ ──┼─► bundle.zip                                                   │
 │                            ▼                                                                │
 │   core.writer (OllamaProvider) ─► manual.json ─► core.render ─► HTML/PDF/DOCX "To'liq"      │
 └─────────────────────────────────────────────────────────────────────────────────────────────┘
         blueprint.json yoki bundle.zip: odam yuklab oladi va server veb-formasida yuklaydi
                      (dasturlar o'rtasida tarmoq aloqasi yo'q)
                                               ▼
 ┌──────────────────────── SERVER DASTUR (server/, Django, Docker) ────────────────────────────┐
 │  A:  yuklangan blueprint ─────► core.explorer ─┐                                             │
 │  A': yuklangan bundle ────────────────────────►├─► core.writer (ClaudeProvider) ─► render    │
 │  B:  URL ─► scout ─► blueprint ► core.explorer ┘                                             │
 └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 3. Sxemalar (`yoriqnoma_schemas`, pydantic v2)

Barcha modellarda `model_config = ConfigDict(extra="forbid")`. Har bir faylning ildizida `schema_version: Literal["1.0"]` maydoni bor.

### 3.1. Umumiy tiplar

```python
RoleId = str                        # "guest" — mehmon; boshqalari saytdagi rol id'si: "customer", "manager"
RoleKind = Literal["guest", "role", "excluded"]      # TZ FR-RL2
Access = Literal["guest", "roles", "excluded", "unknown"]
Stage = Literal["start", "core", "manage", "social", "payment", "settings", "exit"]
Environment = Literal["staging", "production"]
Source = Literal["code", "discovered", "merged"]

class Target(BaseModel):            # kamida bittasi to'ldiriladi; ustuvorlik shu tartibda
    role: str | None = None         # "button", "textbox", "link", ...
    name: str | None = None         # accessible name
    label: str | None = None
    testid: str | None = None
    css: str | None = None          # oxirgi chora

class BBox(BaseModel): x: float; y: float; w: float; h: float
```

### 3.2. Policy

```python
class Policy(BaseModel):
    target_role: RoleId               # yo'riqnoma yozilayotgan rol (TZ FR-RL3)
    helper_roles: list[RoleId] = []   # obyekt tayyorlash uchun yordamchi rollar (masalan, test mijoz; SEC-5)
    deny_paths: list[str]           # glob: "/admin*", "/api/admin*", ...
    deny_action_words: list[str]    # "o'chirish", "удалить", "delete", "to'lash", "оплатить", "pay", ...
    default: Literal["deny"] = "deny"
    environment: Environment = "staging"
    destructive: Literal["own_objects_only", "never"] = "own_objects_only"
    payments: Literal["sandbox_only", "never"] = "sandbox_only"
    test_accounts: int = 2
    max_states: int = 400
    max_depth: int = 3
    requests_per_second: float = 2.0
```

### 3.3. Blueprint

```python
class RoleInfo(BaseModel):
    id: RoleId; label: str                             # "manager", "Menejer"
    kind: RoleKind; reason: str; source: str           # nega role/excluded ekani va qayerdan topilgani
    self_signup: bool = False                          # vosita o'zi ro'yxatdan o'ta oladimi (FR-RL4)
    description: str | None = None                     # variant kartasi uchun qisqa tavsif

class RouteInfo(BaseModel):
    path: str; kind: Literal["page", "api"]; methods: list[str]
    access: Access; roles: list[RoleId] = []; reason: str; source: str          # "app/api/orders.py:42"

class FormField(BaseModel):
    name: str; label: str | None; type: str            # text|email|password|tel|number|select|file|...
    required: bool = False; rules: str | None = None   # "min:8|max:64|regex:..."
    options: list[str] | None = None

class Form(BaseModel):
    id: str; page_path: str; fields: list[FormField]
    submit: Target; api: str | None                    # "POST /api/orders"

class EntityStatus(BaseModel):
    value: str; label: str | None; reachable_by: list[RoleId]; set_by: list[str]  # route manbalari

class Entity(BaseModel):
    name: str; source: str; owner_field: str | None
    pii_fields: list[str] = []                         # begona shaxs ma'lumoti bo'lishi mumkin bo'lgan maydonlar: full_name, phone, email, address...
    actions: list[str]                                 # create, view, list, update, delete, cancel, pay, ...
    statuses: list[EntityStatus] = []
    confidence: float = 1.0

StepAction = Literal["goto", "click", "fill", "select", "check", "upload",
                     "expect_url", "expect_text", "expect_visible",
                     "verify_email", "wait_for", "human_input"]

class Step(BaseModel):
    action: StepAction
    target: Target | None = None
    path: str | None = None            # goto/expect_url uchun; "{own:order_id}" bo'lishi mumkin
    data: str | None = None            # "fake:full_name" | "fake:email" | "fake:phone_uz" |
                                       # "fake:password" | "fake:text" | "literal:..." | "own:<entity>_id"
    text: str | None = None
    rules: str | None = None
    confirm: bool = False              # tasdiqlash tugmasi (production'da shu yerda to'xtaydi)
    destructive: bool = False
    payment: bool = False

class Flow(BaseModel):
    id: str; title: str; stage: Stage; role: RoleId   # faqat kind="guest" yoki "role" bo'lgan rol
    entity: str | None = None; action: str | None = None
    requires: list[str] = []; account: Literal["A", "B"] = "A"
    source: str; status: Literal["unverified", "verified", "failed", "skipped"] = "unverified"
    confidence: float = 1.0; steps: list[Step]

class Blueprint(BaseModel):
    schema_version: Literal["1.0"]; project: str; base_url: HttpUrl
    source: Source; generated_at: datetime; generator: str
    language: str = "uz"; policy: Policy
    roles: list[RoleInfo]               # topilgan barcha rollar, excluded ham (sababi bilan)
    pages: list[RouteInfo]; forms: list[Form]; entities: list[Entity]; flows: list[Flow]
    nav: list[dict[str, str]] = []      # menyu: {label, path}
    i18n: dict[str, str] = {}           # kalit → o'zbekcha matn
    excluded: list[RouteInfo] = []      # hisobot uchun
```

**Validatorlar:**
- `requires` dagi id'lar mavjud bo'lishi kerak;
- graf sikl'siz bo'lishi kerak;
- `excluded` ichida faqat `access="excluded"` route'lar;
- `pages` ichida `access="excluded"` yo'q;
- `flow.role` va `route.roles` dagi id'lar `roles` da bor va `kind="excluded"` emas.

### 3.4. Capture

```python
class Element(BaseModel):
    marker: int; role: str; name: str; bbox: BBox
    selector: Target; kind: Literal["button", "link", "input", "select", "tab", "menu", "other"]
    enabled: bool = True

class NetCall(BaseModel): method: str; path_template: str; status: int

class State(BaseModel):
    id: str; hash: str; url: str; title: str
    flow_id: str | None; step_index: int | None; account: Literal["A", "B", "guest"]
    images: dict[Literal["clean", "som"], str]          # capture/images/ ga nisbiy yo'l
    elements: list[Element]; aria: str
    entity: str | None = None; entity_status: str | None = None
    patched: bool = False; network: list[NetCall] = []
    hidden: list[BBox] = []                            # FR-E10: xiralashtirilgan joylar (rolga tegishli emas yoki almashtirib bo'lmagan qiymat)
    substituted: int = 0                               # FR-E10: almashtirilgan begona qiymatlar soni (qiymatlarning o'zi saqlanmaydi)
    kept_public: int = 0                               # FR-E10: topilgan, lekin tashkilot yoki nashr zonasida bo'lgani uchun o'z holicha qoldirilganlar soni

class FlowResult(BaseModel):
    flow_id: str; status: Literal["verified", "failed", "skipped"]
    reason: str | None; state_ids: list[str]; duration_s: float

class BlockedRequest(BaseModel): method: str; url: str; rule: str; at: datetime

class CaptureRun(BaseModel):
    schema_version: Literal["1.0"]; run_id: str; blueprint_hash: str
    role: RoleId                                       # maqsadli rol
    base_url: HttpUrl; environment: Environment; started_at: datetime; finished_at: datetime | None
    flows: list[FlowResult]; states: list[State]
    firewall_log: list[BlockedRequest]; own_objects: dict[str, list[str]]   # entity → id'lar
    test_values: list[str] = []                        # datagen yaratgan barcha qiymatlar (o'z va almashtirilgan); PII tekshiruvi ularni o'tkazib yuboradi
    public_values: list[str] = []                      # FR-E10: umumiy deb qoldirilgan qiymatlar (tashkilot, nashr); PII tekshiruvi ularni ham o'tkazib yuboradi
```

### 3.5. Manual

```python
class StepText(BaseModel): n: int; text: str; image: str | None; markers: list[int] = []
class StatusRow(BaseModel): status: str; meaning: str; what_you_can_do: str; patched_image: bool = False

class Article(BaseModel):
    flow_id: str; title: str; purpose: str
    steps: list[StepText]; notes: list[str] = []
    statuses: list[StatusRow] = []; needs_review: bool = False

class Section(BaseModel):
    id: str; stage: Stage | Literal["reference", "faq", "unverified"]
    title: str; intro: str; articles: list[Article]

class RefEntry(BaseModel): page_title: str; path: str; purpose: str; elements: list[str]
class QA(BaseModel): q: str; a: str

class CoverageItem(BaseModel): kind: str; key: str; covered: bool; reason: str | None
class Coverage(BaseModel): percent: dict[str, float]; items: list[CoverageItem]

class Manual(BaseModel):
    schema_version: Literal["1.0"]; project: str; language: str
    role: RoleId; role_label: str                      # yo'riqnoma qaysi rol uchun
    generated_at: datetime; source_mode: Literal["A", "A'", "B", "A+B", "local"]
    models: list[str]; sections: list[Section]
    reference: list[RefEntry]; faq: list[QA]; coverage: Coverage
```

## 4. Asosiy interfeyslar

### 4.1. LLM provider (`core.writer.providers.base`)

```python
T = TypeVar("T", bound=BaseModel)

@dataclass(frozen=True)
class LLMRequest:
    task: str                      # "describe_page", "describe_statuses", "notes", "faq", "intro", "agent_step"
    system: str
    prompt: str
    images: list[Path] = field(default_factory=list)
    max_tokens: int = 2048
    temperature: float = 0.0
    cacheable_prefix: str | None = None   # Claude prompt caching uchun

@dataclass
class LLMResult(Generic[T]):
    data: T; model: str; input_tokens: int; output_tokens: int
    cost_usd: float | None; latency_s: float; cached: bool

class LLMProvider(Protocol):
    name: str
    def capabilities(self) -> set[str]: ...            # {"vision", "json_schema"}
    async def generate(self, req: LLMRequest, schema: type[T]) -> LLMResult[T]: ...
```

**Implementatsiyalar:**

- **`FakeProvider`** — deterministik. Javoblarni `tests/fixtures/llm/<task>/<hash>.json` dan oladi yoki sxemadan namuna yasaydi.
- **`OllamaProvider`** — `ollama.AsyncClient(host)` bilan ishlaydi:
  - chaqiruv: `chat(model, messages=[{role, content, images}], format=schema.model_json_schema(), options={temperature, num_ctx}, keep_alive)`;
  - javob `schema.model_validate_json()` bilan tekshiriladi;
  - `show(model)` orqali `vision` imkoniyati tekshiriladi.
- **`ClaudeProvider`** — `anthropic.AsyncAnthropic` bilan ishlaydi:
  - chaqiruv: `messages.parse(model, max_tokens, system=[{type: text, text, cache_control: {type: ephemeral}}], messages=[...base64 image blocks..., text], output_format=schema)`;
  - natija `response.parsed_output` dan olinadi;
  - `response.usage` bo'yicha narx hisoblanadi;
  - model tanlash konfiguratsiyadan: `task → model`.

**Kesh** (`writer.cache`): kalit `sha256(task + prompt_version + model + prompt + images_hash)`, qiymat `.cache/llm/<kalit>.json` fayli. DB ishlatilmaydi.

### 4.2. Skaner parseri (`scanner.parsers.base`)

```python
class Parser(Protocol):
    name: str
    def applies(self, project: ProjectInfo) -> bool: ...
    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult: ...

@dataclass
class ParseResult:
    routes: list[RouteCandidate]       # path, kind, methods, guards: list[GuardInfo], source
    forms: list[Form]; entities: list[EntityCandidate]
    flows: list[Flow]; nav: list[NavItem]; i18n: dict[str, str]; notes: list[str]

@dataclass
class GuardInfo:
    kind: Literal["role", "ownership", "auth", "unknown"]; expr: str; source: str
```

**`SafeFS`:**
- `read_text(path) -> str | None`. Taqiqlangan, binar yoki 2 MB dan katta fayl uchun `None` qaytaradi va sababini `skipped` ro'yxatiga yozadi.
- `iter_files(globs)` — taqiqlangan papkalarga kirmaydi.
- **Boshqa hech qanday fayl o'qish usuli ishlatilmaydi.** Testda `builtins.open` kuzatilib, `.env` ochilmagani tekshiriladi.

### 4.3. Tadqiqotchi

```python
class Mailbox(Protocol):                       # MailpitMailbox(api_url) | DirMailbox(path)
    async def wait_for(self, to: str, timeout_s: int = 60) -> MailMessage: ...

class HumanInput(Protocol):                    # lokal: DbHumanInput / terminal; server: JobHumanInput
    async def ask(self, kind: Literal["sms_code", "captcha", "confirm"], message: str) -> str: ...

class PolicyEngine:
    def allows_path(self, path: str) -> bool
    def allows_request(self, method: str, url: str, resource_type: str, ctx: RunContext) -> tuple[bool, str]
    def allows_click(self, el: Element, ctx: RunContext) -> tuple[bool, str]

class StepExecutor:
    async def execute(self, step: Step, ctx: RunContext) -> StepOutcome
```

**Runner tartibi:**
1. `accounts.ensure(role, A, B)` — maqsadli roldagi akkauntlarni (kerak bo'lsa yordamchi rol akkauntini ham) tayyorlaydi.
2. `privilege_check` — akkaunt maqsadli rolda ekanini va admin yoki adminga o'xshash huquqi yo'qligini tekshiradi.
3. `topo_sort(flows)` — maqsadli rolning flow'larini bog'liqlik bo'yicha tartiblaydi.
4. Har bir flow bajariladi: qadamlar, har qadamdan keyin `capture.snapshot()`.
5. `state_graph.explore(page)` — holatlar grafi.
6. `patching.render_unreachable_statuses()` — yetib bo'lmaydigan statuslar.
7. `capture.write()` — natijani yozadi.

Resume uchun holat `capture/progress.json` faylida saqlanadi.

**Lokator strategiyasi** (birinchi topilgani ishlatiladi):
1. `get_by_role(role, name=name, exact=True)`
2. `get_by_label`
3. `get_by_test_id`
4. `locator(css)`

Element topilmasa, flow `failed` bo'ladi va sababi yoziladi.

**Elementlarni yig'ish:**
- JS orqali ko'rinadigan interaktiv elementlar olinadi: `a`, `button`, `input`, `select`, `textarea`, `[role=button|tab|menuitem|link]`, `[onclick]`.
- Har biri uchun: accessible name va bbox.
- Markerlar o'qish tartibida beriladi: avval y, keyin x bo'yicha.
- Matn uchun `page.locator("body").aria_snapshot()`.

**Xiralashtirish va almashtirish (TZ FR-E10).** Skrinshot maqsadli rol akkauntida olinadi. Umumiy ma'lumotlar va test akkauntning o'z ma'lumotlari o'z holicha qoladi. Boshqa ikki holat:
- **Rolga tegishli bo'lmagan element** — `PolicyEngine` taqiqlagan yoki blueprint bo'yicha boshqa rol yoki `excluded` route'ga olib boradigan havola va bloklar (masalan, ekranda ko'rinib qolgan "Admin panel"). Ular `State.hidden` ga yoziladi, rasmda xiralashtiriladi va matnga kirmaydi.
- **Begona shaxs ma'lumoti** — `explorer/pseudonymize.py` uni skrinshotdan oldin to'qima qiymat bilan almashtiradi:
  0. **Zona.** `explorer/zones.py` har bir topilgan qiymatning DOM'dagi joyiga qarab zonasini aniqlaydi (TZ FR-E10), birinchi mos kelgani olinadi:
     - `own` — test akkauntning o'z obyekti (`own_objects`, `test_values`) → o'z holicha;
     - `user_content` — schema.org `Comment`/`Review`/`UserComments`, `comment`/`review`/`reply`/`izoh`/`sharh`/`отзыв` sinf va id'lari, blueprint'da `self_signup` rol yaratadigan obyekt → almashtiriladi;
     - `org` — `base_url` domeni yoki uning subdomenidagi email; `header`, `footer`, `nav`, `[role=banner]`, `[role=contentinfo]`; «Aloqa» va «Biz haqimizda» sahifalari (`/contact`, `/about`, `/aloqa` va nav'dagi nomi bo'yicha) → o'z holicha;
     - `editorial` — `article`, schema.org `Article`/`NewsArticle`/`BlogPosting` sahifasining asosiy qismi, muallif imzosi (`/author/`, `rel=author`, `itemprop=author`), reklama bloklari → o'z holicha. Agar shu turdagi kontentni `self_signup` rol yarata olsa (blueprint flow'lari yoki B rejimida topilgan forma), `user_content` hisoblanadi;
     - `other` — qolgan hamma joy → test akkauntniki bo'lmasa almashtiriladi; zona aniqlanmasa ham shu (default-deny).

     `org` va `editorial` qiymatlari `CaptureRun.public_values` ga, soni `State.kept_public` ga yoziladi.
  1. **Tarmoq darajasi.** Saytning o'z API'si qaytargan JSON javoblar `route.fetch()` → o'zgartirish → `route.fulfill()` orqali o'tadi (`patching` bilan bir xil mexanizm). `Entity.pii_fields` dagi va nomidan aniqlangan (`name`, `full_name`, `email`, `phone`, `address`, `card`, `passport`, `avatar`...) maydonlar, agar obyekt test akkauntniki bo'lmasa (`owner_field`, `own_objects`, `test_values` bo'yicha) va obyekt nashr yoki tashkilot obyekti bo'lmasa, `datagen` qiymatlariga almashtiriladi. Foydalanuvchi kontenti obyektlarida matn maydonlari (`text`, `body`, `comment`...) ham to'qima matnga almashtiriladi.
  2. **DOM darajasi** (server-rendered saytlar va qolganlar uchun). Skrinshotdan oldin `pii.find_pii` matn tugunlari va maydon qiymatlarida `test_values` da yo'q qiymatlarni topadi. Ismlar tuzilmadan ham topiladi: muallif elementlari, jadvalning ism ustunlari (sarlavhasi «Ism», «F.I.Sh», «Mijoz», «ФИО», «Name»...), `itemtype=Person` ichidagi `itemprop=name`. Zona `user_content` yoki `other` bo'lsa, qiymat JS bilan to'qima qiymatga almashtiriladi. Begona odamning profil rasmi neytral avatar bilan almashtiriladi.
  3. **Rasm ichidagi matn.** `explorer/ocr.py` (RapidOCR, `rapidocr-onnxruntime`, Apache 2.0, offline, CPU) skrinshotdagi har bir rasm, canvas, fon rasmi va video kadri (≥ 48×16 px) ichidagi matnni o'qiydi; natija rasm xeshi bo'yicha keshlanadi. OCR matnida `pii.find_pii` ishlaydi, qaror rasm turgan zonaga qarab qabul qilinadi. `user_content` yoki `other` zonasida topilgan matn joyi xiralashtiriladi va `State.hidden` ga sababi bilan yoziladi.
  4. **Zaxira.** Boshqa yo'l bilan almashtirib bo'lmagan qiymat (canvas, PDF ko'rinishi) xiralashtiriladi va `State.hidden` ga yoziladi; sabab hisobotga tushadi.
  5. **Yakuniy tekshiruv.** Skrinshotdan keyin aria va element nomlarida `pii.find_pii` qayta ishlaydi; `test_values` va `public_values` dan boshqa topilma bo'lsa, `mask_text` qilinadi va holat hisobotda belgilanadi.

**To'qima qiymatni hisoblash** (`datagen.substitute`). Jadval saqlanmaydi: qiymat har safar qayta hisoblanadi.
- `seed = HMAC-SHA256(pseudonym_key, run_id + kind + normalize(real))`. Bir xil haqiqiy qiymat bitta ish ichida, to'xtab qayta boshlanganda ham, doim bitta to'qima qiymat beradi. Boshqa ishda boshqa qiymat chiqadi, shuning uchun ishlarni bir-biriga bog'lab bo'lmaydi.
- Bitta yozuvdagi (JSON obyekt, jadval qatori, kartochka) qiymatlar bitta to'qima odamdan olinadi: kalit sifatida yozuvdagi eng barqaror identifikator olinadi (email, keyin telefon, keyin ism).
- `normalize` email'ni kichik harfga, telefonni faqat raqamlarga keltiradi, ismdagi ortiqcha bo'shliqlarni olib tashlaydi.
- Kalit faqat `ExploreOptions.pseudonym_key` orqali beriladi, `core` uni o'zi o'qimaydi. Lokalda u `var/pseudonym.key` faylida turadi va birinchi ishga tushishda yaratiladi. Serverda u `YORIQNOMA_PSEUDONYM_KEY` env'ida turadi. Kalit capture, bundle, log va yo'riqnomaga yozilmaydi.
- `datagen` yaratgan barcha qiymatlar `CaptureRun.test_values` da saqlanadi. Begona obyektlarga DELETE, PUT va PATCH baribir firewall'da to'xtaydi (SEC-4), shuning uchun almashtirilgan qiymat saytga qaytib yozilmaydi.

### 4.4. Renderer

`render.build(manual, capture_dir, out_dir, formats={"html", "pdf", "docx"}) -> RenderResult`

- **HTML** Jinja2 orqali yaratiladi.
- **PDF** shu HTML'dan olinadi: `page.pdf(format="A4", display_header_footer=True)`.
- **DOCX** python-docx bilan alohida quriladi.
- Rasmlarda faqat `State.hidden` joylari xiralashtiriladi (TZ FR-E10); spotlight atrofni biroz qorong'ilashtiradi, lekin o'qiladigan qoldiradi.

## 5. Ishlash papkasi

**Lokal dasturda** papka `local/var/runs/<project_slug>/<run_id>/` da yaratiladi. **Serverda** xuddi shu tuzilma MinIO'da `jobs/<job_id>/` prefiksi ostida saqlanadi.

```
<run_dir>/
  blueprint.json  scan_report.md  overrides.json
  capture/capture.json  capture/images/<state_id>_{clean,som}.png  capture/progress.json
  bundle.zip                                   # faqat "Bundle" natijasida
  manual.json
  dist/html/index.html  dist/html/assets/  dist/html/images/
  dist/manual.pdf  dist/manual.docx  dist/coverage_report.html
  logs/run.jsonl
```

`run_id` formati: `YYYYMMDD-HHMMSS-<6 belgi>`.

`core.pipeline` funksiyalari faqat papka va obyektlar bilan ishlaydi. Django haqida hech narsa bilmaydi:

```python
async def run_explore(blueprint: Blueprint, run_dir: Path, opts: ExploreOptions,
                      human: HumanInput, progress: ProgressSink, cancel: CancelToken) -> CaptureRun
async def run_write(run_dir: Path, provider: LLMProvider, progress: ProgressSink, cancel: CancelToken) -> Manual
def run_render(run_dir: Path, formats: set[str]) -> RenderResult
```

`ProgressSink` va `CancelToken` protokollari dasturlarda implementatsiya qilinadi: lokalda Run/RunEvent orqali, serverda Job/JobEvent orqali.

## 6. Lokal dastur (`local/`, Django)

### 6.1. Ishga tushirish

`uv run yoriqnoma-local` (`yoriqnoma_local.launcher:main`) quyidagilarni bajaradi:
1. `migrate` va tizim tekshiruvlari (FR-L11).
2. Veb-server: **waitress**, `127.0.0.1:8765`.
3. Huey worker: `manage.py run_huey -w 2 -k thread` — alohida jarayonda.
4. Brauzerni ochadi.
5. `Ctrl+C` ikkalasini to'xtatadi.

**Asosiy sozlamalar:**
- `ALLOWED_HOSTS = ["127.0.0.1", "localhost"]`, `DEBUG=False` (`--dev` bayrog'i bilan `True`).
- Baza: `local/var/local.sqlite3`.
- Huey: `SqliteHuey("yoriqnoma", filename="local/var/huey.sqlite3")`.
- `MEDIA_ROOT = local/var/runs`.
- `LANGUAGE_CODE="uz"`, `TIME_ZONE="Asia/Tashkent"`.
- Fernet kaliti `local/var/secret.key` faylida, birinchi ishga tushishda yaratiladi.
- Almashtirish (HMAC) kaliti `local/var/pseudonym.key` faylida, u ham birinchi ishga tushishda yaratiladi (TZ FR-E10).

### 6.2. Modellar

```python
class AppSettings(models.Model):          # yagona yozuv (singleton)
    ollama_host = URLField(default="http://127.0.0.1:11434"); ollama_model = CharField(default="gemma4:26b")
    num_ctx = IntegerField(default=24576); language = CharField(default="uz")

class Project(models.Model):
    name; slug; source_dir = CharField(blank=True)          # bo'sh bo'lsa: blueprint qo'lda yuklanadi
    base_url = URLField(); environment = CharField(choices=staging|production)
    mailbox_kind = CharField(choices=mailpit|dir); mailbox_target = CharField()
    language = CharField(default="uz"); created_at

class ProjectAccount(models.Model):
    project = FK(Project); role = CharField(); alias = CharField(choices=A|B); login; password_enc = BinaryField()

class BlueprintVersion(models.Model):
    project = FK; created_at; scanner_version; source = CharField(choices=scan|upload)
    path = CharField()                    # var/runs/.../blueprint.json
    report_path = CharField(blank=True); overrides = JSONField(default=dict)   # {"exclude_pages": [...], "exclude_flows": [...], "rename_flows": {...}}
    stats = JSONField(default=dict); is_current = BooleanField()

class Run(models.Model):
    project = FK; blueprint = FK(BlueprintVersion)
    role = CharField(blank=True)          # maqsadli rol; "blueprint" natijasida bo'sh (barcha rollar)
    output = CharField(choices=full|blueprint|bundle)
    status = CharField(choices=queued|running|waiting_input|done|failed|cancelled)
    stage = CharField(choices=explore|write|render|package, blank=True)
    progress_done = IntegerField(default=0); progress_total = IntegerField(default=0)
    model = CharField(blank=True); formats = JSONField(default=list)
    run_dir = CharField(); stats = JSONField(default=dict); error = TextField(blank=True)
    cancel_requested = BooleanField(default=False)
    created_at; started_at; finished_at

class RunEvent(models.Model): run = FK; at; level; stage; message
class InputRequest(models.Model): run = FK; kind; message; value_enc = BinaryField(null=True); created_at; answered_at
```

### 6.3. Ish oqimi

1. **Loyiha yaratish.**
2. **"Skanerlash".** Huey vazifasi `scan_project` → `scanner.scan()` → yangi `BlueprintVersion`.
3. **"Blueprint'ni ko'rib chiqish".** Birinchi tab — «Rollar»: topilgan rollar, tasnifi va sababi. Overrides HTMX orqali saqlanadi. `scanner.overrides.apply(blueprint, overrides)` faqat **kamaytiradi**: sahifa yoki flow'ni chiqaradi, nomini o'zgartiradi. `excluded` dagi narsani qaytara olmaydi.
4. **"Ishga tushirish"** — avval maqsadli rol variantlardan tanlanadi (TZ FR-RL3: "Saytda administratordan boshqa N ta rol topildi. Qaysi rol uchun yo'riqnoma yozay?"), keyin natija turi:
   - **`blueprint`** — darhol: overrides qo'llangan `blueprint.json` yoziladi, `Run.status=done`.
   - **`bundle`** — Huey `execute_run` → `core.pipeline.run_explore` → `explorer.bundle` → `bundle.zip`.
   - **`full`** — `run_explore` → `run_write(OllamaProvider)` → `run_render`.
5. **(ixtiyoriy) Natijani serverga olib o'tish — qo'lda.** Foydalanuvchi ish sahifasidan `blueprint.json` yoki `bundle.zip` ni yuklab oladi va server veb-sahifasidagi `/jobs/new/` formasida o'zi yuklaydi. Lokal dastur serverga ulanmaydi, server manzili va kalitini bilmaydi.

**Implementatsiyalar:**
- `DbProgressSink` — `RunEvent` yozadi va `Run.progress_*` ni yangilaydi.
- `DbCancelToken` — `Run.cancel_requested` ni o'qiydi.
- `DbHumanInput` — `InputRequest` yaratadi, javobni har 2 soniyada tekshiradi, timeout 10 daqiqa.

### 6.4. Sahifalar (URL)

| URL | Sahifa |
|---|---|
| `/` | Loyihalar ro'yxati, tizim holati (Ollama, Playwright) |
| `/projects/new/`, `/projects/<id>/edit/` | Loyiha formasi (kod papkasi, base URL, muhit, akkauntlar, pochta) |
| `/projects/<id>/` | Loyiha: oxirgi blueprint, ishlar tarixi, tugmalar |
| `POST /projects/<id>/scan/` | Skanerlashni boshlash |
| `/projects/<id>/blueprint/` | Ko'rib chiqish: Rollar · Sahifalar · Obyektlar · Flow'lar · Chiqarib tashlanganlar · Hisobot (tablar, HTMX tugmalar) |
| `POST /projects/<id>/blueprint/upload/` | Kodsiz loyiha uchun tayyor blueprint yuklash |
| `/projects/<id>/runs/new/` | Rol variantlari (kartalar, bir yoki bir nechta), natija turi (3 ta radio karta), model, formatlar |
| `/runs/<id>/` | Progress (`/runs/<id>/status/` partial, har 2 s), log, input formasi, bekor qilish, natijalar (yuklab olish; blueprint/bundle uchun "server sahifasida yuklang" ko'rsatmasi) |
| `/runs/<id>/files/<name>` | Yuklab olish (faqat `run_dir` ichidagi fayllar, path traversal himoyasi) |
| `POST /runs/<id>/open-folder/` | Papkani ochish: Windows'da `os.startfile`, Linux'da `xdg-open` |
| `/settings/` | Ollama (host, model ro'yxati, ulanish testi) |
| `/eval/` | Modellarni solishtirish natijalari |

### 6.5. Boshqaruv buyruqlari

```
manage.py scan    --project <slug> | --path DIR --base-url URL  [--out FILE]
manage.py explore --project <slug> --role <id> [--blueprint FILE]
manage.py write   --run <id> [--model gemma4:26b]
manage.py render  --run <id> [--formats html,pdf,docx]
manage.py run     --project <slug> --output full|blueprint|bundle [--role <id> ...] [--list-roles] [--model ...]
manage.py bundle  --run <id> --out bundle.zip
manage.py eval    --golden tests/golden/ --models gemma4:26b,qwen3.6:27b
```

Buyruqlar UI bilan bir xil `services.py` funksiyalarini chaqiradi. Terminalda `HumanInput` — `input()` orqali.

## 7. Server dastur (`server/`, Django)

### 7.1. Komponentlar (docker compose)

| Servis | Vazifasi |
|---|---|
| `caddy` | TLS (Let's Encrypt), reverse proxy, statik fayllar |
| `web` | Django (gunicorn): HTMX sahifalar, DRF API, `/ops/` admin |
| `worker` | Celery worker: Playwright + core + scout. Root'siz, `mem_limit`, `cpus`, egress firewall, `concurrency = MAX_CONCURRENT_JOBS`, `prefetch=1`, `acks_late` |
| `beat` | Celery beat: muddati o'tganlarni tozalash, osilib qolgan ishlarni tekshirish |
| `postgres` | **Faqat** server ma'lumotlari: users, keys, domains, jobs, events, artifacts |
| `redis` | Celery broker |
| `minio` | Rasmlar, bundle'lar, natijalar (django-storages S3) |
| `mailpit` | Catch-all test pochta: `*@inbox.<server-domeni>`, MX yozuvi serverga yo'naltiriladi |
| `demo_shop` | Faqat `test` profilida: poligon nishon sifatida (`../local/fixtures/demo_shop` dan build) |

### 7.2. Modellar

```python
# accounts: Django'ning standart User modeli (ro'yxatdan o'tish, kirish). API kalitlar yo'q.

# domains
class Domain(models.Model):
    owner = FK(User); host; token; verified_at = DateTimeField(null=True)
    method = CharField(choices=wellknown|meta|dns, blank=True)

# jobs
class Job(models.Model):
    owner = FK(User); domain = FK(Domain)
    mode = CharField(choices=A|A_PRIME|B|A_PLUS_B); url; environment; language; formats = JSONField()
    role = CharField()                                       # maqsadli rol (TZ FR-RL3)
    status = CharField(choices=queued|preflight|scouting|exploring|writing|rendering|waiting_input|done|failed|cancelled)
    progress_done; progress_total
    budget_usd = DecimalField(); cost_usd = DecimalField(default=0); tokens_in; tokens_out
    accounts_enc = BinaryField(null=True)
    blueprint = FileField(null=True); bundle = FileField(null=True)
    passive = BooleanField()                                 # domen tasdiqlanmagan bo'lsa True
    source = CharField(choices=web|api); error = TextField(blank=True); cancel_requested = BooleanField(default=False)
    created_at; started_at; finished_at; expires_at

class JobEvent(models.Model): job = FK; at; kind = CharField(status|progress|log|need_input|artifact|cost); payload = JSONField()
class InputRequest(models.Model): job = FK; kind; message; value_enc; created_at; answered_at
class Artifact(models.Model): job = FK; name; file = FileField(); size; sha256
```

### 7.3. Ish holatlari

```
queued → preflight → (scouting) → exploring → writing → rendering → done
              ↘ waiting_input (SMS, captcha) ↗           ↘ failed | cancelled
```

- `scouting` faqat B va A+B rejimlarida bo'ladi.
- A' rejimida `exploring` o'tkazib yuboriladi.

Hodisalar `JobEvent` da saqlanadi. UI ularni `/jobs/<id>/events/?after=<event_id>` orqali har 2 soniyada HTMX polling bilan oladi. SSE ishlatilmaydi, chunki gunicorn bilan oddiyroq va barqarorroq.

**Celery vazifalari:**
- `jobs.tasks.run_job(job_id)` — rejimga qarab: `scout` → `core.pipeline.run_explore` → `run_write(ClaudeProvider)` → `run_render` → Artifact'lar MinIO'ga.
- `cleanup_expired()` — har kuni.
- `reap_stuck_jobs()` — har 10 daqiqada.

**Implementatsiyalar:** `JobProgressSink`, `JobCancelToken`, `JobHumanInput` (lokaldagi bilan bir xil g'oya).

### 7.4. REST API (DRF, `/api/`)

**Autentifikatsiya:** faqat sessiya + CSRF (login qilgan foydalanuvchi). API kalitlar yo'q, chunki lokal dastur serverga ulanmaydi.

| Metod | Yo'l | Tavsif |
|---|---|---|
| GET, POST | `/api/domains/` | O'z domenlari; POST `{host}` → `{id, token, methods}` |
| POST | `/api/domains/{id}/verify/` | well-known, meta yoki DNS TXT orqali tekshiradi |
| GET, POST | `/api/jobs/` | POST multipart: `mode`, `url`, `environment`, `language`, `formats`, `accounts?`, `blueprint?`, `bundle?`, `budget_usd?` → `{id, web_url, status}` |
| GET | `/api/jobs/{id}/` | Holat, progress, narx, artifact ro'yxati |
| GET | `/api/jobs/{id}/events/?after=` | Hodisalar |
| POST | `/api/jobs/{id}/input/` `{request_id, value}` | SMS kodi va hokazo |
| POST | `/api/jobs/{id}/cancel/` | Bekor qilish |
| GET | `/api/jobs/{id}/artifacts/{name}/` | Qisqa muddatli imzolangan havolaga redirect |

**Ruxsatlar:** har bir obyekt faqat egasiga ko'rinadi (`owner == request.user`).

### 7.5. Veb sahifalar

- **Hisob:** `/accounts/login/`, `/accounts/register/`, `/accounts/logout/`.
- **Domenlar:** `/domains/` — qo'shish, token va 3 xil joylash yo'riqnomasi, "Tekshirish" tugmasi.
- **Ishlar:**
  - `/jobs/` — ro'yxat;
  - `/jobs/new/` — rejim kartalari, URL, muhit, rol variantlari (A: blueprint'dagi rollar; A': bundle'dagi rol; B: akkauntlardan aniqlangan yoki qo'lda kiritilgan rollar) va rol akkauntlari, fayl (lokal dastur yaratgan `blueprint.json` yoki `bundle.zip`), byudjet;
  - `/jobs/<id>/` — bosqichlar, log, narx, input formasi, natijalar.
- **Admin:** `/ops/` — Django admin, faqat staff.

### 7.6. Razvedkachi (B rejimi) — `server/scout`

- **`preflight`** — url_guard; domen tasdiqlanganmi; `robots.txt`; `sitemap.xml`; til; texnologiya belgilari.
- **`crawler`** — faqat shu domen ichida BFS. URL shablonlanadi (`/x/123` → `/x/:id`), har shablondan ≤ 2 namuna olinadi; `deny_paths`; limitlar.
- **`js_routes`** — yuklangan JS bundle'lar va ochiq source map'lardan route satrlari olinadi.
- **`network_infer`** — XHR/fetch so'rovlaridan REST shablonlari va CRUD amallari xaritasi tuziladi.
- **`auth_flow`** — ro'yxatdan o'tish va kirish formalari topiladi (Haiku tasnifi). Test pochta `job-<id>@inbox.<domen>`.
- **`roles`** — berilgan har bir akkaunt bilan kirib, ko'rinadigan menyu va sahifalardan rolni aniqlaydi; ro'yxatdan o'tishdagi rol tanlovini topadi; adminga o'xshash belgilar bo'lsa rolni `excluded` qiladi (TZ FR-RL1, FR-RL2).
- **`agent`** — Claude Sonnet, tool use. Tool'lar: `goto(path)`, `click(marker)`, `fill(marker, value_kind)`, `select(marker, option)`, `back()`, `finish_flow(title, stage, entity, action)`, `give_up(reason)`.
  - Har bir tool chaqiruvi `PolicyEngine` dan o'tadi.
  - Byudjet limiti: sahifa, qadam va dollar.
- **`validation_probe`** — o'z ma'lumotida bo'sh yoki noto'g'ri qiymat yuboriladi, xato xabarlari yig'iladi.
- **`blueprint_builder`** — `source="discovered"`, `confidence` bilan.
- **`merge`** — A+B: kod ma'lumoti ustun, discovered faqat yangi narsalarni qo'shadi.

## 8. Konfiguratsiya

**Lokal dastur.** Sozlamalar `AppSettings` (baza) va `local/var/` papkasida. Env orqali qayta yozish mumkin:
- `YORIQNOMA_LOCAL_PORT` (standart 8765);
- `YORIQNOMA_VAR_DIR` (standart `local/var`);
- `YORIQNOMA_HUEY_WORKERS`.

**Server dastur** (django-environ, env fayllar faqat serverning o'zida, git'da faqat `*.example` shablonlar):
- Qiymatlar Docker compose `env_file` orqali beriladi. Django `.env` faylini o'zi o'qimaydi, shuning uchun `manage.py` buyruqlari konteyner ichida ishga tushiriladi: `docker compose exec web python manage.py ...`.
- Ikki fayl bor:
  - `docker/.env` — Claude kalitidan boshqa barcha qiymatlar, hamma servislar uchun;
  - `docker/worker.env` — faqat `ANTHROPIC_API_KEY`, faqat `worker` servisiga beriladi (TZ SEC-12).
- `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_SETTINGS_MODULE=yoriqnoma_server.settings.prod`
- `DATABASE_URL`, `REDIS_URL`
- `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- `ANTHROPIC_API_KEY` — faqat `docker/worker.env` da. Bo'sh bo'lsa worker ishga tushmaydi.
- `YORIQNOMA_USER_DAILY_BUDGET_USD`, `YORIQNOMA_USER_MONTHLY_BUDGET_USD`, `YORIQNOMA_MONTHLY_BUDGET_USD` — umumiy xarajat limitlari (TZ FR-SV6)
- `YORIQNOMA_FERNET_KEY`
- `YORIQNOMA_PSEUDONYM_KEY` — begona shaxs ma'lumotini almashtirish uchun HMAC kaliti (TZ FR-E10)
- `YORIQNOMA_MAIL_DOMAIN`, `YORIQNOMA_PUBLIC_URL`
- `YORIQNOMA_MAX_CONCURRENT_JOBS`, `YORIQNOMA_RETENTION_DAYS`
- `YORIQNOMA_MODEL_HAIKU=claude-haiku-5-5`, `YORIQNOMA_MODEL_SONNET=claude-sonnet-5-5`, `YORIQNOMA_MODEL_OPUS=claude-opus-5-5`
- `YORIQNOMA_PRICES` (JSON: model → $/MTok input, output, cache read, cache write)

## 9. Testlash strategiyasi

| Daraja | Qayerda | Marker |
|---|---|---|
| Unit | `<dastur>/packages/*/tests`, `<dastur>/<ilova>/tests` (pytest-django) | — |
| Integratsion | demo_shop ishga tushiriladi (pytest fixture, port 8800) | `slow` |
| LLM | Haqiqiy Ollama yoki Claude | `llm` |
| Server e2e | docker compose (`--profile test`) | `server` |

- **Ishga tushirish:** har bir dastur o'z papkasida (`cd local` yoki `cd server`): `uv run pytest` — kutubxonalar, `tests/` va Django ilovalari bitta jarayonda; `uv run mypy` — strict, django-stubs bilan.
- **Django sozlamalari testlarda:**
  - lokal uchun Huey `immediate=True` (`yoriqnoma_local.settings_test`);
  - server uchun `CELERY_TASK_ALWAYS_EAGER=True`; unit testlar SQLite'da, `server` marker testlari compose'dagi PostgreSQL'da.
- **Oltin to'plam** `local/tests/golden/`: 20–30 holat (rasm + elementlar) va kutilgan natija belgilari.
- **`tests/test_shared_copies.py`** (ikkala dasturda bir xil): `schemas` va `core` ning lokal va server nusxalari bayt-ma-bayt bir xil; `scanner` serverda yo'q.
- **`tests/test_no_db_drivers.py`** (ikkala dasturda bir xil): `packages/scanner` va `packages/core` ning manba kodida (AST) va `pyproject` bog'liqliklarida `sqlite3`, `psycopg`, `pymysql`, `sqlalchemy`, `sqlmodel`, `asyncpg`, `aiosqlite`, `django` bo'lmasligi tekshiriladi.

## 10. Poligon: `local/fixtures/demo_shop`

**Maqsadi:** barcha komponentlarni boshqariladigan, ichida ataylab admin qismi ham bor sayt ustida sinash.

**Stek:**
- backend: FastAPI + SQLite (poligonning **o'z** bazasi);
- frontend: React (Vite, React Router v6), build qilingan `dist/` repoga commit qilinadi, shuning uchun Node faqat qayta build uchun kerak;
- ishga tushirish: `local/` papkasida `uv run demo-shop` (port 8800). Server `docker compose --profile test` ham shu papkadan build qiladi.

**Rollar** (rol tanlash va FR-E10 ni sinash uchun):
- `customer` — mijoz, o'zi ro'yxatdan o'tadi (pastdagi "Foydalanuvchi qismi");
- `manager` — barcha buyurtmalarni ko'radi va `paid` → `shipped` qiladi (`/staff/orders`);
- `courier` — o'ziga biriktirilgan buyurtmalarni ko'radi va `shipped` → `delivered` qiladi (`/courier`);
- `admin` — foydalanuvchilar, rollar va sozlamalar (`/admin*`): adminga o'xshash, topilmasligi kerak.

Seed'da `manager` va `courier` test akkauntlari bor: ular sayt egasi beradigan akkauntlarni taqlid qiladi.

**FR-E10 ni sinash uchun ma'lumotlar** (har biri natijada qanday chiqishi kerakligi bilan):
- footer'da do'konning o'z aloqa ma'lumotlari: `info@demo-shop.uz`, `+998 71 200-00-00` — tashkilot zonasi, o'z holicha qoladi;
- `/catalog/:id` da seed mijozlarining sharhlari (ism, matn) — foydalanuvchi kontenti, almashtiriladi;
- boshqa mijoz buyurtmasiga ilova qilingan rasm (yetkazish varaqasi: ichida ism va telefon) — menejer ko'radi, OCR bilan topilib xiralashtiriladi.

**Foydalanuvchi qismi:**
- **Ochiq sahifalar:** `/`, `/catalog`, `/catalog/:id` (mahsulot sharhlari bilan; sharh yozish — kirgan mijoz uchun)
- **Hisob:** `/register`, `/login`, `/verify-email`, `/forgot-password`
- **Shaxsiy kabinet:**
  - `/app/dashboard`
  - `/app/orders`, `/app/orders/new`
  - `/app/orders/:id` — tablar: "Tafsilotlar" va "Tarix"; tugmalar: bekor qilish (tasdiqlash modali bilan), to'lash (sandbox), chekni yuklab olish
  - `/app/messages` — A va B o'rtasida yozishmalar
  - `/app/profile`
  - `/app/settings` — parol, bildirishnomalar, til
  - `/app/account/delete`

**Buyurtma statuslari:**
- `new` → `paid` (user bajaradi);
- `paid` → `shipped` (manager), `shipped` → `delivered` (courier);
- `paid` → `refunded` (faqat admin);
- `new` → `cancelled` (user bajaradi).

**Admin qismi (topilmasligi kerak):**
- `/admin`, `/admin/users`, `/admin/roles`, `/admin/orders/:id/refund`;
- `/api/admin/*` — `Depends(require_admin)` bilan himoyalangan;
- React'da `<RequireAdmin>` komponenti; xodim sahifalari `<RequireRole role="manager">` va `<RequireRole role="courier">` bilan.

**Pochta:** SMTP orqali Mailpit'ga yuboriladi. Mailpit bo'lmasa, `./var/mail/*.eml` papkasiga yoziladi (`DirMailbox`).

**Skaner uchun tuzoqlar:**
- `.env` (soxta sirlar bilan, Skaner ochmasligi kerak);
- `var/demo.db`.

**Qo'shimcha manbalar:**
- E2E testlar: `e2e/test_register.py` (Playwright Python) va `e2e/order.spec.ts` (Playwright TS);
- i18n: `web/src/locales/uz.json`, `web/src/locales/ru.json`.

**Validatsiya qoidalari:**
- parol ≥ 8 belgi;
- telefon `+998XXXXXXXXX` formatida;
- buyurtma miqdori 1–99.

## 11. Amalga oshirish holati va farqlar (2026-11-09)

Lokal dastur (F0–F4, T00–T20, T29, T30) va server dastur (F5–F6, T21–T28) qurildi. Lokal dastur demo_shop'da to'liq tekshirildi. Server: unit va sekin testlar (demo_shop, haqiqiy brauzer, Claude o'rnida FakeProvider) yashil; docker compose bilan e2e testlar yozilgan, lekin Docker va Claude kaliti bo'lgan mashinada ishga tushirilishi kerak. Quyidagilar yuqoridagi tavsifdan farq qiladi yoki uni to'ldiradi:

**Sxemalar** (`schema_version` "1.0" qoldi: hali hech qanday iste'molchi yo'q, yangi maydonlarning hammasi ixtiyoriy):
- `Entity`: `status_field` (API javobidagi status maydoni), `created_by` (yaratadigan rollar).
- `Flow`: `creates` (yangi id own_objects'ga yoziladi), `sets_status`, `needs_status` (obyekt qaysi holatda bo'lishi kerak: tadqiqotchi kerak bo'lsa yordamchi rol bilan yangi obyekt tayyorlaydi).
- `State`: `hidden: list[HiddenArea]` (BBox + `reason`), `privacy` ("zona:qaror" → soni), `parent_id`, `trigger`, `viewport`.
- `FlowResult`: `role`, `helper`, `stopped_at_confirm`. `CaptureRun`: `role_label`, `project`, `privilege_ok`, `notes`.
- `Manual`: `role_granted_by` (to'liq gap), `Section.empty_reason`, `StepText.state_id`, `StatusRow.image`.
- `Step.data` qo'shimcha qiymatlari: `fake:option` (ro'yxatning birinchi varianti), `fake:address`, `fake:date`, `peer:email` (ikkinchi akkaunt emaili). `expect_url` yo'li `re:` bilan boshlansa — regex.
- `DEFAULT_DENY_ACTION_WORDS` ga chiqish so'zlari qo'shildi (`chiqish`, `logout`, `выйти`): holatlar grafi sessiyani yopmasligi uchun.

**Skaner:** Python kodi stdlib `ast` bilan (`pyindex.py` — modullar va importlarni hal qilish), JS/TS `tree-sitter` + `tree-sitter-javascript`/`tree-sitter-typescript` bilan o'qiladi (language-pack o'rniga). E2E parserlari bitta `parsers/e2e.py` faylida. zod/yup qoidalari `parsers/zod_yup.py` da (`zodResolver`, `yupResolver`, Formik `validationSchema`), react-hook-form `register('x', {...})` qoidalari `jsx_forms.py` da. Flow'lar rol bo'yicha nomlanadi: `customer.order.pay`, `manager.order.ship`.

**Skaner, Django (T29):** `parsers/django_routes.py` (urls, view'lar, guard'lar, DRF, shablonlar), `parsers/django_models.py` (modellar, `forms.py`, serializer'lar), `parsers/html_forms.py` (server shablonlari: Django, Jinja, Blade — forma, tugma, havola, modal ochuvchi), `parsers/i18n.py` da `.po` o'quvchi. Server-rendered view bitta yo'lda ikki xil yoziladi: `page` (GET, komponent = view) va `api` (POST va boshqalar; ro'yxat yoki tafsilot ko'rsatsa GET ham, `entity_hint` bilan). Kutubxona shabloni bilan ishlaydigan Django auth sahifalari (parolni tiklash va h.k.) loyihada shablon bo'lmasa olinmaydi va hisobotga yoziladi. Ruxsat noaniq bo'lsa (`permission_required`, `get_permissions()`, tushunarsiz dekorator) — `unknown`, ya'ni chiqarib tashlanadi. Sinov loyihasi: `fixtures/demo_django` (yordam markazi: `customer`, `support`, admin).

**Skaner, Flask (T29):** `parsers/flask_routes.py` — Django parserining shablon, komponent va route chiqarish qismidan foydalanadi (view'lar bir xil ko'rinishda). Ikkala parser uchun umumiy tekshiruvlar `parsers/pyviews.py` da: tanadagi rol/admin tekshiruvi (`raise`, `abort(403)`, `redirect`, `Response(status=4xx)`), loyiha dekoratorlari, egalik filtri (`filter(owner=request.user)`, `filter_by(user_id=current_user.id)`), status o'rnatish va shartlari. Flask-SQLAlchemy modellari (`db.Model`, `__tablename__` siz) `sqlalchemy_models.py` da.

**Sxemalar 1.1 (2026-11-08):** `schema_version: Literal["1.0", "1.1"]`, yangi fayllar 1.1; 1.0 fayllar o'qilaveradi (faqat ixtiyoriy maydonlar qo'shildi): `Element.css` (sahifadagi CSS yo'li, tur uchun), `CaptureRun.pseudonym_scope` (to'qima qiymatlar doirasi — ish id'si, sir emas).

**T30:** `writer/changes.py` — oldingi ish bilan solishtirish: ekranlar DOM xeshi bilan emas, tuzilma imzosi bilan (sahifa shabloni + boshqaruv elementlarining turi va nomi), chunki xesh har ishning test akkauntlari va to'qima qiymatlari bilan o'zgaradi; natija `changelog.md`. Yangilash ishi oldingi ishning `pseudonym_scope` ini oladi (`DataGen(scope=...)`): bir xil begona odam bir xil to'qima qiymat oladi, o'zgarmagan ekranlar promptlari bir xil bo'lib, matn keshdan olinadi; test akkauntlari esa har ishda yangi. `render/tour.py` — Driver.js turlari (`Element.css`, yo'llar `:id` shablon bilan, rasm markerlari olib tashlanadi), `render/gif.py` — har maqola uchun GIF. Formatlar: `DEFAULT_FORMATS` (html, pdf, docx) va qo'shimcha `tour`, `gif`. `ExploreOptions.device_scale_factor` (lokal dasturda 2.0): rasm koordinatalari CSS pikselda qoladi, rasm kodi masshtabni o'zi hisoblaydi. Lokal: `Run.previous`, «Oldingi natija asosida yangilash» tugmasi, `run --previous`. CI namunasi: `docs/ci/github-action.yml`.

**Skaner, JS va PHP steklari (T29):** `parsers/express_routes.py` (tree-sitter; router'lar fayllar bo'ylab, middleware guard'lari, controller'lar, Mongoose/Sequelize, EJS), `parsers/vue_app.py` (Vue Router `meta`, `.vue` komponentlar), `parsers/nextjs.py` (fayl asosidagi route'lar, middleware matcher, layout va handler tekshiruvlari; sahifa komponenti JSX parseridan default eksport nomi bilan), `parsers/laravel.py` (PHP matn sifatida, qavslarni hisobga oladigan kichik tokenizer: route guruhlari, resource, middleware, controller, migratsiya, Blade), `parsers/prisma_models.py`. Backend va model parserlari alohida ishlaydi, shuning uchun "yangi foydalanuvchining standart roli" (`SIGNUP_DEFAULT`) va rollar topilmagan saytdagi `user` roli `api._finish_roles` da hal qilinadi; guard'dagi `admin` modeldagi `ADMIN` bilan bitta rolga birlashtiriladi. Inertia sahifalari va Pug shablonlari hali o'qilmaydi.

**Tadqiqotchi (server-rendered saytlar):** imtiyoz tekshiruvida admin sahifasi login'ga (yoki boshqa ochiq sahifaga) yo'naltirsa, bu rad etish hisoblanadi. Foydalanuvchi kontenti obyektlarida (o'zi ro'yxatdan o'tadigan rol yaratadi) jadval ustunlari yaratish formasidagi matn maydonlari nomi bilan («Mavzu») aniqlanadi va begona qatorda almashtiriladi. Begona obyektning server-rendered tafsilot sahifasi (JSON'siz) olinmaydi: undagi erkin matnni sahifa matnidan ajratib bo'lmaydi (default-deny, `CaptureRun.notes` ga yoziladi).

**Tadqiqotchi:** holatlar grafi va yamalgan statuslar `explorer/runner.py` ichida (`_state_graph`, `_patched_statuses`); JS kodlari `explorer/js.py` da; `ExploreOptions` va protokollar `explorer/options.py` da. Chiqish va hisobni o'chirish flow'lari eng oxirida, yamalgan statuslar va holatlar grafidan keyin bajariladi. Ro'yxat sahifasidan bitta-ikkita boshqa foydalanuvchi yozuvi ochiladi (ma'lumotlari almashtirilgan holda). `datagen` Faker'siz: o'zbekcha ism va manzillar ro'yxati bilan. OCR matnidagi yo'qolgan bo'shliqlar hisobga olinadi («Qabulqiluvchi:...»).

**Yozuvchi:** javob sxemalari `writer/answers.py` da. Ollama'da `think=False`; model takrorlanib qolsa (`repeat limit`), bir marta `temperature=0.4` bilan qayta so'raladi. Prompt versiyasi `tasks.PROMPT_VERSION`. Modellar solishtiruvi (`manage.py eval`, 25 holat, RTX 3090, 2026-11-08): gemma4:26b — sxema xatosi 0, marker xatosi 3, taqiqlangan so'z 0, kalit so'z qamrovi 79%, o'rtacha 2,0 s; qwen3.6:27b — 0, 5, 2 (yo'q «administrator»ni o'ylab topdi), 73%, 3,7 s. Asosiy model: gemma4:26b; qwen muqobil sifatida qoladi (ikkalasida ham vision bor).

**Renderer:** rasmlar 1x (2x retina hali yo'q), PNG + WebP. Qidiruv indeksi `search_index.json` va `file://` da ishlashi uchun `search_index.js`.

**Lokal dastur:** boshqaruv buyruqlari `runs/management/commands/` da (qo'shimcha `account` buyrug'i — test akkaunt qo'shish) va `evaluation/management/commands/eval.py`. Statik fayllar waitress orqali Django'ning o'zidan beriladi (`var/static`, faqat 127.0.0.1). Pipeline Huey thread'ida `asyncio.run` bilan, ORM chaqiruvlari alohida DB thread'ida. Oltin to'plam: `local/tests/golden/` — 25 holat (24 tasi demo_shop, 1 tasi demo_django). OCR modeli lotin: kirill matni buzilib o'qiladi («MBaHOB»), shuning uchun begona zonadagi rasmda bunday yoki kirill qatori ism bo'lishi mumkin deb xiralashtiriladi (default-deny, `ocr.unreadable`).

**Core (server uchun):** `ExploreOptions.passive` — tasdiqlanmagan domen (SEC-9): faqat mehmon flow'lari, ular ham faqat o'qiydigan qadamlar bilan (`goto`, `click`, `expect_*`); `PolicyEngine(passive=True)` GET'dan boshqa so'rovni bloklaydi; yamalgan statuslar va login yo'q. `url_guard.HostGuard` — brauzerning har bir so'rovi hostini (redirect, boshqa domendagi resurs, websocket) qayta tekshiradi, DNS javoblari 60 soniya keshlanadi; `Firewall(guard=...)` bilan lokalda ham ishlaydi (lokalda `allow_private=True`, lekin metadata va link-local baribir yopiq).

**Server, umumiy:** sozlamalar `settings/{base,dev,prod,test,e2e}.py`. Claude kaliti Django sozlamasi emas: uni faqat worker muhiti va `jobs.pipeline` o'qiydi; worker `worker_init` signalida kalitlarsiz to'xtaydi (`yoriqnoma_server/worker_env.py`); web jarayonida kalit bo'lsa `security.W001` ogohlantiradi. `YORIQNOMA_PRIVATE_ALLOWLIST` — faqat e2e profili (`demo_shop`) va sekin testlar uchun; `prod.py` uni har doim bo'sh qiladi. Natijalar MinIO'da; yuklab olish `S3_PUBLIC_ENDPOINT_URL` bo'lsa 5 daqiqalik imzolangan havola, bo'lmasa egasi tekshirilgach Django faylni o'zi uzatadi.

**Server, ishlar (`jobs/`):** `services.create_jobs` — har tanlangan rol uchun alohida ish; `budget.check_budget` — ishlayotgan ishlar butun byudjeti bilan, tugaganlari haqiqiy narxi bilan hisoblanadi; `uploads.py` — blueprint va bundle tekshiruvi (core `verify_bundle` ustiga: manifestda yo'q fayl, symlink, `C:` yo'llar, yetishmayotgan rasmlar); `pipeline.execute` — rejimlar zanjiri, ish papkasi worker'da vaqtinchalik (`var/jobs/<id>`), tugagach o'chadi, parollar o'chiriladi; artifact'lar: `manual.pdf`, `manual.docx`, `manual-html.zip`, `coverage_report.html`, `manual.json`, `blueprint.json`, `tour.zip`, `gif.zip`. ORM chaqiruvlari pipeline ichida alohida DB thread'da (`sinks.DbThread`). Hodisalar: `status`, `log`, `need_input`, `artifact`, `cost`.

**Server, xavfsizlik (`security/`):** `ssrf.safe_get` — serverning o'z HTTP so'rovlari: har redirect tekshiriladi, ulanish tekshirilgan IP'ga (DNS pinning, SNI va `Host` sarlavhasi asl host bilan); `ratelimit` — GCRA, Redis'da (Lua) yoki xotirada; `robots` — passiv rejimda `Disallow` yo'llari `deny_paths` ga qo'shiladi, B rejimi crawler'i ularga kirmaydi; `logfilter.SecretsFilter` — barcha log handler'larida. Login urinishlari django-axes bilan (5 marta, 1 soat). CSP (django-csp 4): faqat o'z statik fayllari, inline skript yo'q — shuning uchun «Yangi ish» formasidagi rejim maydonlari CSS `:has()` bilan almashadi.

**Server, B rejimi (`scout/`):** `kit.ScoutKit` — core'ning brauzer sessiyasi, firewall va almashtirish (PrivacyLedger) qismlaridan; `crawler` — tarmoq javoblaridan faqat JSON kalit nomlari olinadi; `auth_flow` — kirish va ro'yxatdan o'tish formalari (so'zlar bo'yicha, noaniq bo'lsa Haiku), tasdiqlash xatidagi kod formasi topiladi va `verify_email` qadami unga yoziladi; `agent` — Claude tool use'i LLMProvider orqali structured output sifatida (`AgentAction`), har amal PolicyEngine'dan o'tadi, formaga faqat vositaning o'z to'qima qiymatlari yoziladi, production va passiv rejimda forma to'ldirilmaydi; `validation_probe` — rol sahifalaridagi formaga bo'sh qiymat yuborib, saytning o'z xato xabarlarini `msg:` qoidasi sifatida oladi (faqat staging); `blueprint_builder` — mehmonga ochilgan sahifa `guest`, faqat kirgandan keyin ochilgan sahifa maqsadli rol, admin'ga o'xshash yo'l va faqat JS'da ko'ringan sahifa `excluded`; `merge` — A+B. Razvedka akkaunti identiteti: `<rol>.s.<xesh>@<YORIQNOMA_MAIL_DOMAIN>`. Har bir ishning agent byudjeti: ish byudjetining `YORIQNOMA_SCOUT_AGENT_SHARE` qismi (standart 40%).

**Lokal dastur: uch rejim (FR-L13, SEC-18).** `Project.mode`: `code`, `code_admin`, `admin`; admin login `Project.admin_login` + `admin_password_enc` (Fernet) + `admin_path`. «Tekshirish» (`projects.services.check_project`, Huey vazifasi, sahifa HTMX bilan kutadi): kod skani (1, 2) va admin rollari (`projects.admin_access.check_admin`). 2-rejimda koddagi rol admin roli bilan moslanadi (`BlueprintVersion.stats["admin_roles"]`), 3-rejimda faqat rollardan iborat blueprint saqlanadi (`source="admin"`). Ish (`runs.services.explore_with_test_users`): `ProvisionSession.create` — maqsadli rol uchun A va B, 2-rejimda kerakli yordamchi rollar uchun A; 3-rejimda `discover_blueprint` (core `discovery.run.discover_site`, Ollama bilan) yangi blueprint (`source="discovered"`) yaratadi; keyin `run_explore`; `finally` ichida `ProvisionSession.cleanup(own_objects)`, natija `Run.stats["cleanup"]` da. Qayta tozalash: `/runs/<id>/cleanup/`, `manage.py cleanup --run <id>`.

**Core `provision/`:** `base` (AdminCredentials, RoleCandidate, CreatedUser, Ledger — `provision.json`), `guard.ProvisionGuard` (admin sessiyasi firewall'i, yangi id'lar javobdan o'rganiladi), adapterlar — `django_admin.DjangoAdminAdapter` (login, foydalanuvchi modeli admin indeksidan, rol: `role`-ga o'xshash select yoki `groups`, add → change formasi, `<model>/<id>/delete/`), `form_admin.FormAdminAdapter` (parol + email + rol maydoni bor forma, ro'yxatdagi qatorning o'chirish tugmasi), `agent_admin.AgentAdminAdapter` (Ollama, faqat boshqalari mos kelmasa), `provisioner.Provisioner` (alohida brauzer, adapter tanlash, rollar, yaratish, tozalash).

**Core `discovery/`:** serverning `scout` paketidagi Django'siz qismlar shu yerga ko'chirildi (`urls`, `js_routes`, `forms`, `network_infer`, `crawler`, `auth_flow`, `blueprint_builder`, `merge`, `kit`, `agent`, `validation_probe`, `run`). Rate limit, robots.txt, JS fayllarni olish va LLM provayder dasturdan beriladi. Serverda faqat `scout/preflight.py` va `scout/discover.py` (safe_get, Redis rate limit, Claude) qoldi.

**Server, deploy (`server/docker/`):** worker ikki tarmoqda: `internal` (internetsiz; postgres, redis, minio, mailpit) va `egress` (internet, `egress-firewall.sh` qoidalari bilan). Har ish alohida jarayonda (`--max-tasks-per-child=1`); har ish uchun alohida konteyner emas (SEC-11 shu darajada). Batafsil: `docs/DEPLOY.md`.
