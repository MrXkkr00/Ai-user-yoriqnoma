# Texnik topshiriq: AI_user_yoriqnoma

Versiya 1.1 · 2026-11-07 (ikki Django dasturi: Lokal va Server)

## 1. Umumiy ma'lumot

**1.1. Nomi.** AI_user_yoriqnoma — foydalanuvchi yo'riqnomasi generatori.

**1.2. Maqsad.** Veb-sayt yoki veb-tizimni avtomatik o'rganish va **oddiy foydalanuvchi rolining barcha imkoniyatlarini** qamraydigan, matn va rasmli, qadamma-qadam yo'riqnoma yaratish. Tizimni kodi orqali yoki faqat URL orqali o'rganish mumkin.

Yo'riqnomani o'qigan odam saytdan to'liq foydalana olishi kerak:
- ro'yxatdan o'tish va kirish;
- asosiy ishlar;
- o'z ma'lumotlarini boshqarish va statuslar;
- to'lovlar va muloqot;
- sozlamalar va hisobni o'chirish.

**1.3. Kimlar foydalanadi:**

| Kim | Vaziyat | Ishlatadigan dastur va natija |
|---|---|---|
| Ishlab chiquvchi yoki jamoa | Kodi bor, hammasi lokal bo'lsin | Lokal → "To'liq yo'riqnoma" |
| Ishlab chiquvchi yoki jamoa | Kodi bor, sayt internetda, Claude sifati kerak | Lokal → "Blueprint" → Server A |
| Ichki tarmoqdagi tizim egasi | Server saytga kira olmaydi | Lokal → "Bundle" → Server A' |
| Sayt egasi | Kodi qo'lida yo'q | Server B (faqat URL) |

**1.4. Til.** Yo'riqnoma o'zbek tilida (lotin yozuvi) yaratiladi. Shablonlar i18n tuzilmasida, keyinchalik ru/en qo'shiladi.

## 2. Atamalar

| Atama | Ma'nosi |
|---|---|
| Blueprint | Saytning foydalanuvchi funksiyalari xaritasi (`blueprint.json`) |
| Flow | Bitta foydalanuvchi vazifasining qadamlari (masalan, "Buyurtmani bekor qilish") |
| Obyekt (entity) | Userga tegishli ma'lumot turi (buyurtma, post, ariza) |
| Capture | Tadqiqotchi yig'gan holatlar, skrinshotlar va natijalar (`capture.json` + rasmlar) |
| Manual | Yo'riqnomaning tuzilgan ko'rinishi (`manual.json`) |
| SoM | Set-of-Mark — skrinshot ustidagi raqamli markerlar |
| Test akkaunt | Vosita yaratgan yoki egasi bergan **oddiy** (admin emas) akkaunt |
| Default-deny | Noaniq holatda taqiqlash |
| Yamalgan javob | Test user yeta olmaydigan statusni ko'rsatish uchun o'z obyekti javobida faqat `status` maydonini almashtirish |

## 3. Tizim tarkibi

Tizim **ikkita dastur** va ular birga ishlatadigan **uchta kutubxona paketidan** iborat.

| Dastur | Ichidagi qismlar | Texnologiya | Qayerda | Internet |
|---|---|---|---|---|
| **Lokal dastur** (oldingi 1.0 + 2.1) | Skaner, Tadqiqotchi, Yozuvchi (Ollama), Renderer | Django 5.2, Huey, SQLite | Foydalanuvchi kompyuteri, `127.0.0.1` | Kerak emas |
| **Server dastur** (oldingi 2.2) | Razvedkachi, Tadqiqotchi, Yozuvchi (Claude), Renderer | Django 5.2, DRF, Celery, PostgreSQL, MinIO | Onlayn server (Docker) | Kerak |

| Paket | Vazifa | Kim ishlatadi |
|---|---|---|
| `yoriqnoma_schemas` | Blueprint, capture, manual sxemalari | Ikkala dastur |
| `yoriqnoma_scanner` | Kod → `Blueprint` | Lokal dastur |
| `yoriqnoma_core` | Tadqiqotchi, Yozuvchi, Renderer, xavfsizlik | Ikkala dastur |

**Lokal dasturda natija turlari** (har ishda foydalanuvchi tanlaydi):

| Natija turi | Bajariladigan bosqichlar | Natija | Keyin nima qilinadi |
|---|---|---|---|
| **To'liq yo'riqnoma** | Skan → tadqiqot → yozish (Ollama) → render | HTML, PDF, DOCX | Tayyor |
| **Blueprint (server A uchun)** | Skan → blueprint ko'rib chiqish | `blueprint.json` | Serverga yuklanadi, server saytga o'zi kiradi |
| **Bundle (server A' uchun)** | Skan → tadqiqot | `bundle.zip` | Serverga yuklanadi, server faqat yozadi va render qiladi |

**Server rejimlari:**
- **A** — blueprint + URL;
- **A'** — bundle (sayt ichki tarmoqda bo'lganda);
- **B** — faqat URL;
- **A+B** — blueprint asosiy, Razvedkachi bo'sh joylarni to'ldiradi.

Lokal dastur blueprint yoki bundle'ni serverga **to'g'ridan-to'g'ri yubora oladi** (API kalit bilan) yoki fayl sifatida saqlaydi.

## 4. Funksional talablar

### 4.1. Skaner — `yoriqnoma_scanner`, lokal dastur ichida (FR-S)

- **FR-S1. Kirish nuqtasi.**
  - Kutubxona funksiyasi: `scan(project_dir, base_url, stack="auto") -> ScanResult` (blueprint, hisobot, skipped ro'yxati).
  - Lokal dasturda u UI orqali va `manage.py scan` buyrug'i orqali chaqiriladi.
  - Debug uchun: `python -m yoriqnoma_scanner PATH --base-url URL`.
- **FR-S2. Stekni aniqlash.**
  - Bu yerda gap **o'rganiladigan** loyihalar steki haqida, bizning dasturlarimiz haqida emas.
  - MVP: FastAPI + React (Vite, React Router).
  - Keyingi bosqich: birinchi navbatda Django, keyin Flask, Laravel, Vue Router, Next.js, Express.
- **FR-S3. Manbalar:**
  - E2E testlar (Playwright Python/TS, Cypress);
  - route'lar (tree-sitter AST);
  - modellar: egalik maydoni, status enum'lari;
  - formalar va validatsiya: pydantic, zod/yup, HTML atributlari;
  - i18n fayllari;
  - navigatsiya komponentlari.
- **FR-S4. Rol tasnifi.** Har bir route `guest`, `user` yoki `excluded` deb belgilanadi va sababi yoziladi.
  - Admin rol tekshiruvi → `excluded`.
  - Egalik tekshiruvi → `user`.
  - Noaniq → `excluded`, hisobotga ham tushadi.
- **FR-S5. Obyektlar.** Har bir obyekt uchun:
  - amallar (CRUD va maxsus amallar);
  - statuslar;
  - har bir statusga **user yeta oladimi** (`reachable_by_user`). Status faqat admin route'larida o'zgarsa — `false`.
- **FR-S6. Flow'lar.**
  - Har bir obyekt va amal juftligi alohida flow bo'ladi, hisob flow'lari ham qo'shiladi.
  - Har bir flow'ga `requires` va `stage` beriladi.
  - E2E testlardan olingan flow'lar ustun turadi.
- **FR-S7. Chiqish:**
  - `blueprint.json` (sxemaga mos);
  - `scan_report.md`: topilganlar, chiqarib tashlanganlar (sababi bilan) va noaniqlar.
- **FR-S8. Base URL** faqat parametrdan olinadi, hech qanday konfiguratsiya faylidan o'qilmaydi.

### 4.2. Tadqiqotchi — `core.explorer` (FR-E)

- **FR-E1. Kirish ma'lumotlari:**
  - blueprint va base URL;
  - muhit: `staging` yoki `production`;
  - test akkauntlar — ixtiyoriy, bo'lmasa vosita o'zi ro'yxatdan o'tadi;
  - pochta adapteri: Mailpit yoki papka.
- **FR-E2. Akkauntlar.** Ikkita test akkaunt (A, B), har biri alohida toza brauzer kontekstida.
- **FR-E3. Flow'larni bajarish.**
  - Topologik tartibda bajariladi.
  - Har bir qadamdan keyin kutilgan natija tekshiriladi.
  - Natija: `verified`, `failed` yoki `skipped` — sababi bilan.
- **FR-E4. Test ma'lumoti generatori.** Validatsiya qoidalariga mos ma'lumot yaratadi (Faker va qoidalar), seed deterministik.
- **FR-E5. Tasdiqlash.**
  - Email — pochta adapteri orqali.
  - SMS va boshqa kodlar — odam kiritadi: lokal yoki server UI'da, `manage.py` buyruqlarida terminalda.
- **FR-E6. Xavfli amallar** 5-bo'limdagi siyosat bo'yicha bajariladi.
- **FR-E7. Holatlar grafi.**
  - Xavfsiz elementlar bosiladi: tab, accordion, dropdown, modal ochuvchi tugmalar, filtrlar, sahifalash.
  - Takroriy holatlar DOM hash bo'yicha o'tkazib yuboriladi.
  - Chuqurlik va holatlar soniga limit qo'yiladi.
- **FR-E8. Yamalgan javob.** `reachable_by_user=false` statuslar shu usulda ko'rsatiladi. Rasmga `patched=true` belgisi qo'yiladi.
- **FR-E9. Har bir holat uchun yig'iladi:**
  - toza va SoM skrinshot (PNG);
  - elementlar: marker, role, name, bbox, selector;
  - aria snapshot;
  - URL, flow va qadam;
  - obyekt statusi;
  - tarmoq so'rovlari: metod, yo'l shabloni, status kodi. **So'rov tanasi yozilmaydi.**
- **FR-E10. Maskalash.** Skrinshot va matnlardagi email, telefon, ism va karta raqamlari yashiriladi.
- **FR-E11. Chiqish:** `capture/` papkasi (`capture.json` + `images/`) va `bundle.zip`.
- **FR-E12. Davom ettirish (resume).** To'xtab qolgan ish bajarilgan flow'larni qayta bajarmaydi.

### 4.3. Yozuvchi — `core.writer` (FR-W)

- **FR-W1. Provider interfeysi:** `OllamaProvider` (lokal dastur), `ClaudeProvider` (server dastur), `FakeProvider` (testlar). Model nomi konfiguratsiyadan olinadi.
- **FR-W2. Ish taqsimoti.**
  - Qadam matnlari o'zbekcha **shablon** bilan yoziladi.
  - LLM quyidagilarni yozadi: vazifa tavsifi, status tavsiflari, eslatmalar, FAQ, bo'limlar orasidagi bog'lovchi matn.
- **FR-W3. LLM javobi.**
  - Javob faqat JSON sxema bo'yicha olinadi.
  - Tekshiruv: sxemaga mosligi, marker mavjudligi, nomlarning DOM'ga mosligi.
  - Xatoda 2 martagacha qayta uriniladi, keyin `needs_review` belgisi qo'yiladi.
- **FR-W4. Yo'riqnoma tuzilmasi (9 bo'lim):**
  1. Boshlash
  2. Asosiy ishlar
  3. O'z ma'lumotlarini boshqarish (statuslar jadvali bilan)
  4. Boshqa userlar bilan
  5. To'lovlar
  6. Sozlamalar va xavfsizlik
  7. Hisobni o'chirish
  8. Imkoniyatlar ma'lumotnomasi (A–Z)
  9. Xatolar va FAQ
- **FR-W5. Faqat tasdiqlangan flow'lar.** Yo'riqnomaga faqat `verified` flow'lar kiradi. `failed` flow'lar "Tekshirilmagan" ilovasiga tushadi.
- **FR-W6. Qamrov hisoboti.**
  - Foiz hisoblanadi: user yo'llari, formalar, tugmalar, amallar, statuslar bo'yicha.
  - Qamralmaganlar ro'yxati sababi bilan chiqariladi.
- **FR-W7. Kesh.** Bir xil kirish (holat hash + prompt versiyasi + model) uchun LLM qayta chaqirilmaydi. Kesh fayllarda saqlanadi.

### 4.4. Renderer — `core.render` (FR-R)

- **FR-R1. Yo'riqnoma rasmlari** modelga berilgan rasmdan alohida chiziladi (Pillow):
  - maqsad atrofida qirqim;
  - spotlight;
  - raqamli belgilar;
  - strelka.
- **FR-R2. HTML.** Offline ishlaydigan bitta papkali sayt: mundarija va lokal qidiruv (JS indeks).
- **FR-R3. PDF.** Playwright `page.pdf()` orqali: A4, sahifa raqamlari. WeasyPrint ishlatilmaydi, chunki Windows'da GTK talab qiladi.
- **FR-R4. DOCX.** python-docx orqali: sarlavha uslublari, rasmlar va izohlar, mundarija maydoni.
- **FR-R5. Qamrov hisoboti** `coverage_report.html` ko'rinishida.

### 4.5. Lokal dastur — Django (FR-L)

- **FR-L1. Ishga tushirish.**
  - `uv run yoriqnoma-local` bitta buyruq bilan ikkita narsani ishga tushiradi: veb-server (waitress, `127.0.0.1:8765`) va Huey worker.
  - Keyin brauzer avtomatik ochiladi.
  - Dastur faqat `127.0.0.1` da tinglaydi (`ALLOWED_HOSTS` = localhost).
- **FR-L2. O'z bazasi.** `var/local.sqlite3` — loyihalar, ishlar, hodisalar va sozlamalar uchun. Test akkaunt parollari Fernet bilan shifrlanadi, kalit `var/secret.key` faylida.
- **FR-L3. Loyiha.** Har bir loyiha uchun saqlanadi:
  - nomi;
  - kod papkasining yo'li (ixtiyoriy — kodsiz loyihada faqat bundle uchun qo'lda yozilgan blueprint yuklash mumkin);
  - base URL va muhit (staging yoki production);
  - test akkauntlar (ixtiyoriy);
  - pochta adapteri (Mailpit URL yoki papka);
  - til.
- **FR-L4. Natija turini tanlash.** Har bir ishni boshlashda foydalanuvchi uchtadan birini tanlaydi:
  - **To'liq yo'riqnoma** — skan → blueprint ko'rib chiqish → tadqiqot → yozish (Ollama) → render (HTML, PDF, DOCX);
  - **Blueprint (server A uchun)** — skan → ko'rib chiqish → `blueprint.json`;
  - **Bundle (server A' uchun)** — skan → ko'rib chiqish → tadqiqot → `bundle.zip`.
- **FR-L5. Blueprint ko'rib chiqish.** Skandan keyin foydalanuvchi quyidagilarni ko'radi va o'zgartira oladi:
  - sahifalar, obyektlar va flow'lar ro'yxati;
  - istalgan sahifa yoki flow'ni **chiqarib tashlash** mumkin, lekin `excluded` qilinganini qo'shib bo'lmaydi (default-deny saqlanadi);
  - flow nomini o'zgartirish mumkin.

  O'zgarishlar alohida "override" sifatida saqlanadi va blueprint'ga qo'llaniladi.
- **FR-L6. Ollama.**
  - Asosiy model `gemma4:26b`, muqobil `qwen3.6:27b`. Model sozlamalar sahifasida tanlanadi; o'rnatilgan modellar ro'yxati Ollama'dan olinadi.
  - Sozlamalar: `temperature=0`, `num_ctx` 16384–32768, `format` ga JSON sxema, `keep_alive`.
  - Modelda `vision` imkoniyati borligi tekshiriladi.
- **FR-L7. Ish sahifasi.**
  - Bosqichlar va progress ko'rinadi (HTMX, 2 soniyada yangilanadi).
  - Jonli log.
  - SMS kodi va boshqa ma'lumotlarni kiritish formasi.
  - Ishni bekor qilish.
  - To'xtab qolgan ishni davom ettirish (resume).
- **FR-L8. Natijalar.**
  - HTML yo'riqnomani ochish;
  - PDF, DOCX, `blueprint.json`, `bundle.zip` va hisobotlarni yuklab olish;
  - natija papkasini ochish (Windows Explorer).
- **FR-L9. Serverga yuborish.** Sozlamalarda server URL'i va API kalit bo'lsa, blueprint yoki bundle tugma bilan serverga yuboriladi. Server ish havolasini qaytaradi va ish holati lokal sahifada ham ko'rinadi.
- **FR-L10. Boshqaruv buyruqlari** (avtomatlashtirish va CI uchun):

  ```
  manage.py scan | explore | write | render | run --output full|blueprint|bundle | bundle | eval
  ```

  Ular UI bilan bir xil servislarni chaqiradi.
- **FR-L11. Ishga tushish tekshiruvlari.** Ollama ishlayaptimi, model bormi, Playwright chromium o'rnatilganmi, base URL ochiladimi — har biri uchun aniq o'zbekcha yechim xabari chiqariladi.
- **FR-L12. `eval` — modellarni solishtirish.** Oltin to'plamda ikki modelni solishtiradi:
  - sxema xatolari;
  - marker xatolari;
  - vaqt;
  - qo'lda baholash uchun yonma-yon sahifa.

### 4.6. Server dastur — Django (FR-SV)

- **FR-SV1. Rejimlar:** A, A', B, A+B.
- **FR-SV2. Veb-interfeys** (Django shablonlar + HTMX):
  - server foydalanuvchilari uchun ro'yxatdan o'tish va kirish (Django auth);
  - API kalitlarini yaratish va o'chirish (lokal dastur uchun);
  - domen qo'shish va tasdiqlash;
  - ish yaratish;
  - jarayonni jonli kuzatish (HTMX polling);
  - SMS kodini kiritish;
  - natijalarni yuklab olish.
- **FR-SV3. REST API** (DRF) — ARCHITECTURE §7.4 da. Sessiya va API kalit bilan autentifikatsiya qilinadi.
- **FR-SV4. Navbat.** Celery + Redis, worker'lar va Celery beat (davriy vazifalar). Bir vaqtdagi ishlar soni konfiguratsiyada belgilanadi.
- **FR-SV5. Razvedkachi (B rejimi):**
  - preflight;
  - mehmon sifatida aylanish (guest crawl);
  - ochiq JS bundle'lardan route'lar;
  - tarmoq kuzatuvi;
  - kirish yoki ro'yxatdan o'tish;
  - imtiyoz tekshiruvi;
  - Claude agenti (tool use);
  - validatsiyani o'rganish.

  Natija: `blueprint.json` (`source=discovered`, `confidence` bilan).
- **FR-SV6. Claude modellari va xarajat.**
  - `claude-haiku-5-5` — tasniflash;
  - `claude-sonnet-5-5` — agent va tavsiflar;
  - `claude-opus-5-5` — yakuniy tekshiruv.
  - Structured outputs (`messages.parse`) va prompt caching ishlatiladi.
  - Har bir ish uchun token va narx hisoblanadi, byudjet limiti bor.
- **FR-SV7. Saqlash muddati.** Natijalar konfiguratsiyadagi muddat (standart 30 kun) o'tgach o'chiriladi.
- **FR-SV8. Django admin.** Server operatorlari uchun `/ops/` yo'lida joylashadi (`/admin/` emas) va faqat staff'ga ochiq.
- **FR-SV9. Lokal dasturdan qabul qilish.** API kalit bilan `POST /api/jobs` orqali blueprint (A rejimi) yoki bundle (A' rejimi) qabul qilinadi. Javobda ish id'si va veb-havola qaytadi.

## 5. Xavfsizlik talablari (SEC)

- **SEC-1. Default-deny** — barcha komponentlarda.
- **SEC-2. Admin yo'q.** Admin yo'llari, admin huquqlari va boshqa haqiqiy foydalanuvchilar ma'lumotlari hech qachon olinmaydi va ko'rsatilmaydi.
- **SEC-3. Skaner chegaralari.**
  - Fayllar faqat `SafeFS` orqali o'qiladi.
  - **O'qilmaydigan fayllar:** `.env*`, `*.pem`, `*.key`, `*.p12`, `*.sql`, `*.db`, `*.sqlite*`, `*dump*`, `docker-compose*.yml`, `secrets*`, `storage/`, `uploads/`, `logs/`, `node_modules/`, `.git/`, `venv/`, `.venv/`.
  - Skaner va core'da DB drayverlari yo'q, bu test bilan tekshiriladi.
- **SEC-4. Tarmoq firewall'i (Tadqiqotchi).**
  - `deny_paths` ga tushgan so'rovlar bekor qilinadi.
  - Boshqa domenlar: faqat statik resurslar uchun GET'ga ruxsat (stylesheet, script, font, image). Boshqa domenga xhr/fetch, navigatsiya va GET bo'lmagan so'rovlar bekor qilinadi.
  - Test user o'zi yaratmagan obyektga DELETE, PUT yoki PATCH bekor qilinadi.
  - Barcha bloklangan so'rovlar logga yoziladi.
- **SEC-5. Xavfli amallar.**
  - O'chirish, bekor qilish va tahrirlash faqat test user o'zi yaratgan obyektlarda.
  - **Production:** faqat tasdiqlash oynasigacha.
  - **To'lov:** faqat sandbox.
  - **Hisobni o'chirish:** eng oxirida va faqat test akkauntda.
- **SEC-6. Imtiyoz tekshiruvi.** Kirgandan keyin alohida "probe" sahifasida tekshiriladi. Bu sahifada capture o'chirilgan, firewall faqat probe so'rovlariga ruxsat beradi.
  - Admin API'larga yuborilgan so'rov 401, 403 yoki 404 qaytarishi kutiladi.
  - `/admin` sahifasi login'ga qaytarishi yoki 403 ko'rsatishi kutiladi.
  - Admin kontenti ochilsa, ish **to'xtatiladi**.
  - Natija faqat "ha/yo'q" ko'rinishida saqlanadi, sahifa mazmuni saqlanmaydi.
- **SEC-7. Maskalash.** PII maskalanadi. Claude'ga faqat maskalangan ma'lumot yuboriladi.
- **SEC-8. Captcha** avtomatik yechilmaydi, odamdan so'raladi yoki tayyor akkaunt talab qilinadi.
- **SEC-9. Domen tasdiqlash (server).**
  - Usullar: `/.well-known/yoriqnoma-verify.txt` fayli, `<meta name="yoriqnoma-verify">` tegi yoki DNS TXT yozuvi.
  - Tasdiqlanmagan domenda faqat passiv rejim ishlaydi: ro'yxatdan o'tmaydi, forma yubormaydi.
- **SEC-10. SSRF himoyasi.**
  - Faqat `http` va `https`.
  - Hostning **barcha** DNS natijalari tekshiriladi.
  - Bloklanadigan diapazonlar: `0.0.0.0/8`, `10.0.0.0/8`, `100.64.0.0/10`, `127.0.0.0/8`, `169.254.0.0/16`, `172.16.0.0/12`, `192.168.0.0/16`, `224.0.0.0/4`, `::1`, `fc00::/7`, `fe80::/10`.
  - Tekshiruv har bir redirect va Playwright so'rovida qayta bajariladi.
  - Worker konteyneri egress qoidalari bilan cheklanadi.
- **SEC-11. Izolyatsiya.** Har bir ish alohida vaqtinchalik konteynerda: root'siz, CPU, RAM va vaqt limiti bilan.
- **SEC-12. Sirlar.** Test akkaunt parollari Fernet bilan shifrlanadi, ish tugagach o'chiriladi, loglarda maskalanadi.
- **SEC-13. Bundle yuklash.**
  - Hajm limiti (standart 500 MB).
  - Zip slip himoyasi.
  - Faqat `json`, `png`, `jpg`, `webp` fayllari.
  - Sxema bo'yicha tekshiruv.
- **SEC-14. Odob qoidalari.**
  - `robots.txt` hurmat qilinadi.
  - Bitta domenga 1–2 so'rov/soniya.
  - User-Agent: `AI-user-yoriqnoma/<versiya> (+<kontakt URL>)`.
- **SEC-15. Server foydalanuvchilari.**
  - Har kim faqat o'z domenlari, ishlari va API kalitlarini ko'radi.
  - Parollar argon2 bilan saqlanadi (Django `Argon2PasswordHasher`).
  - API kalitlar faqat hash ko'rinishida saqlanadi va faqat yaratilganda bir marta ko'rsatiladi.
- **SEC-16. Lokal dastur.**
  - Faqat `127.0.0.1` da tinglaydi, `ALLOWED_HOSTS` = `localhost`, `127.0.0.1`.
  - CSRF yoqilgan.
  - Kod papkasi yo'li faqat foydalanuvchi o'zi tanlagan papkadan olinadi va `SafeFS` orqali o'qiladi.
- **SEC-17. Server Django sozlamalari.**
  - `DEBUG=False`, `SECURE_*` sozlamalari (HSTS, SSL redirect, secure cookie).
  - `X-Frame-Options`, CSP (django-csp).
  - Login urinishlari cheklanadi (django-axes yoki rate limit).
  - `manage.py check --deploy` toza o'tishi kerak.

## 6. Nofunksional talablar (NFR)

- **NFR-1. Platforma:**
  - lokal dastur — Windows 10/11 va Linux;
  - server dastur — Linux, Docker Compose.
- **NFR-2. Offline.** Lokal dastur "To'liq yo'riqnoma" va "Bundle" natijalarida internetsiz ishlaydi.
- **NFR-3. Apparat (lokal dastur).**
  - Tavsiya: 24 GB VRAM.
  - 16 GB — Q4 modellar bilan.
  - GPU'siz ham ishlaydi, lekin sekin.
- **NFR-4. Unumdorlik** (demo_shop, ~25 sahifa):

  | Bosqich | Maksimal vaqt |
  |---|---|
  | Skan | 30 s |
  | Tadqiqotchi | 15 daqiqa |
  | Lokal yozish, Ollama (RTX 3090) | 30 daqiqa |
  | Server A rejimi (to'liq) | 20 daqiqa |

- **NFR-5. Takrorlanuvchanlik:** seed, `temperature=0`, kesh.
- **NFR-6. Log:** structlog (JSON), maxfiy ma'lumotlarsiz.
- **NFR-7. Sifat.** `packages/` testlar qamrovi ≥ 80%, `apps/` ≥ 60%. ruff, mypy va `makemigrations --check` toza.
- **NFR-8. Litsenziyalar.** Barcha bog'liqliklar ochiq litsenziyali (MIT, BSD, Apache 2.0). Modellar Apache 2.0.

## 7. Kirish va chiqish formatlari

- **Sxemalar:** `blueprint.json`, `capture.json`, `manual.json` — `packages/schemas` da. JSON Schema `docs/schemas/` papkasiga eksport qilinadi.
- **Bitta ishning papkasi** (lokalda `var/runs/`, serverda MinIO'da xuddi shu tuzilma):

  ```
  runs/<project>/<run_id>/
    blueprint.json
    scan_report.md
    capture/ (capture.json, images/)
    manual.json
    dist/ (html/, manual.pdf, manual.docx, coverage_report.html)
    logs/
  ```

## 8. Cheklovlar va farazlar

- Skaner MVP'da o'rganiladigan loyihalarning FastAPI + React stekini qo'llab-quvvatlaydi. Django va boshqa steklar F7 bosqichida qo'shiladi.
- B rejimi faqat sayt orqali ko'rinadigan va topiladigan funksiyalarni qamraydi.
- Admin harakati talab qiladigan holatlar yamalgan javob yoki matn orqali ko'rsatiladi.
- Server-rendered saytlar ham qo'llab-quvvatlanadi, chunki Tadqiqotchi DOM bilan ishlaydi.
- Mobil ilovalar va desktop dasturlar doiradan tashqari.

## 9. Qabul qilish mezonlari (demo_shop poligonida)

- **QM-1. Skaner:**
  - user yo'llarining 100% topiladi;
  - admin yo'llari 0 ta;
  - `.env` fayli ochilmagani testda isbotlangan.
- **QM-2. Tadqiqotchi:**
  - flow'larning ≥ 90% `verified`;
  - admin so'rovlari 0 ta (firewall logi bo'yicha);
  - begona obyektga DELETE 0 ta.
- **QM-3. Yo'riqnoma:**
  - 9 bo'lim mavjud;
  - qamrov ≥ 90%;
  - marker xatolari 0 ta;
  - natijada PII topilmaydi (regex skaner bilan tekshiriladi).
- **QM-4. Lokal dastur:**
  - UI orqali "To'liq yo'riqnoma" Ollama bilan internetsiz boshidan oxirigacha ishlaydi;
  - "Blueprint" va "Bundle" natijalari server sxemasidan o'tadi;
  - "Serverga yuborish" ishlaydi.
- **QM-5. Server dastur:**
  - A, A' va B rejimlari demo_shop'da ishlaydi;
  - SSRF testlari bloklanadi: `127.0.0.1`, `169.254.169.254`, IPv6 loopback, redirect orqali ichki IP;
  - tasdiqlanmagan domenda forma yuborilmaydi.
- **QM-6. B rejimi qamrovi** A rejimiga nisbatan ≥ 70%.

## 10. Bosqichlar

| Faza | Mazmun |
|---|---|
| F0 | Asos: repo, ikkita Django loyiha skeleti, sxemalar, poligon |
| F1 | Skaner paketi |
| F2 | Tadqiqotchi |
| F3 | Yozuvchi va Renderer |
| F4 | Lokal Django dasturi |
| F5 | Server Django dasturi: A va A' rejimlari, Lokal → Server integratsiyasi |
| F6 | Server: B rejimi |
| F7 | Kengaytirish: boshqa steklar, CI, interaktiv tur |

Batafsil vazifalar: `docs/TASKS.md`.
