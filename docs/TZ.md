# Texnik topshiriq: AI_user_yoriqnoma

Versiya 1.2 · 2026-11-10 (ikki Django dasturi: Lokal va Server; lokal dasturda uch rejim, FR-L13)

## 1. Umumiy ma'lumot

**1.1. Nomi.** AI_user_yoriqnoma — foydalanuvchi yo'riqnomasi generatori.

**1.2. Maqsad.** Veb-sayt yoki veb-tizimni avtomatik o'rganish va **tanlangan foydalanuvchi rolining barcha imkoniyatlarini** qamraydigan, matn va rasmli, qadamma-qadam yo'riqnoma yaratish. Tizimni kodi orqali yoki faqat URL orqali o'rganish mumkin.

Saytda bir nechta rol bo'lishi mumkin: oddiy foydalanuvchi (mijoz), menejer, sotuv menejeri, kuryer va hokazo. Vosita administrator va adminga o'xshash (saytni boshqaradigan) rollardan **boshqa barcha rollar** uchun yo'riqnoma yoza oladi. U saytdagi rollarni topadi, ularni variant sifatida ko'rsatadi va qaysi rol uchun yo'riqnoma yozishni so'raydi (FR-RL).

Yo'riqnomani o'qigan odam o'z roli doirasida saytdan to'liq foydalana olishi kerak. Masalan, oddiy foydalanuvchi uchun:
- ro'yxatdan o'tish va kirish;
- asosiy ishlar;
- o'z ma'lumotlarini boshqarish va statuslar;
- to'lovlar va muloqot;
- sozlamalar va hisobni o'chirish.

Menejer kabi xodim rollari uchun esa shu rolning ishlari: masalan, buyurtmalarni ko'rish, statusini o'zgartirish, hisobotlar.

**1.3. Kimlar foydalanadi:**

| Kim | Vaziyat | Ishlatadigan dastur va natija |
|---|---|---|
| Ishlab chiquvchi yoki jamoa | Kodi bor, hammasi lokal bo'lsin | Lokal (1-rejim) → "To'liq yo'riqnoma" |
| Ishlab chiquvchi yoki jamoa | Kodi va admin logini bor, test akkauntlarni qo'lda ochishni xohlamaydi | Lokal (2-rejim) → "To'liq yo'riqnoma" |
| Sayt egasi | Kodi yo'q, admin logini bor, hammasi lokal bo'lsin | Lokal (3-rejim) → "To'liq yo'riqnoma" |
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
| Rol | Saytdagi foydalanuvchi turi: mijoz, menejer, sotuv menejeri va h.k. Har bir rolning o'z sahifalari va huquqlari bor |
| Maqsadli rol | Yo'riqnoma yozilayotgan rol. Ish boshida variantlardan tanlanadi |
| Adminga o'xshash rol | Saytni boshqaradigan rol: administrator, superadmin yoki foydalanuvchilar, rollar, huquqlar va sayt sozlamalarini boshqaradigan har qanday rol. Bunday rollar uchun yo'riqnoma yozilmaydi |
| Test akkaunt | Vosita yaratgan yoki egasi bergan, maqsadli roldagi akkaunt (admin yoki adminga o'xshash emas) |
| Default-deny | Noaniq holatda taqiqlash |
| Yamalgan javob | Maqsadli rol yeta olmaydigan statusni ko'rsatish uchun o'z obyekti javobida faqat `status` maydonini almashtirish |
| Begona shaxs ma'lumoti | Test akkauntga emas, saytdagi boshqa odamga tegishli ma'lumot: boshqa foydalanuvchilarning yozuvlari (profil, buyurtma, ariza, xabar) va ular yozgan kontent — ism, email, telefon, manzil, karta raqami, hujjat raqami (pasport, JSHSHIR), profil rasmi. Tashkilot ma'lumotlari va nashr kontenti bunga kirmaydi |
| Tashkilot ma'lumoti | Saytning o'ziga tegishli ma'lumot: nomi, sayt domenidagi email, rasmiy telefon, manzil, rekvizitlar. Umumiy ma'lumot hisoblanadi |
| Nashr kontenti | Sayt o'z nomidan hamma uchun e'lon qilgan kontent: maqola, yangilik, ularning rasmlari, muallif imzosi, reklama. Umumiy ma'lumot hisoblanadi |
| Foydalanuvchi kontenti | O'zi ro'yxatdan o'tgan foydalanuvchilar yaratgan kontent: izoh, sharh, e'lon, forum posti, xabar. Ochiq sahifada bo'lsa ham begona shaxs ma'lumoti hisoblanadi |
| Zona | Sahifadagi blok turi: tashkilot, nashr, foydalanuvchi kontenti yoki boshqa. Topilgan shaxsiy qiymat shu zonaga qarab qoldiriladi yoki almashtiriladi (FR-E10) |
| Almashtirish | Begona shaxs ma'lumotini rasm va matnda vosita yaratgan, mavjud bo'lmagan test ma'lumoti bilan almashtirish (FR-E10) |

## 3. Tizim tarkibi

Tizim **ikkita dastur** va ular birga ishlatadigan **uchta kutubxona paketidan** iborat.

Repo ham ikki papkaga bo'lingan: `local/` (lokal dastur) va `server/` (server dastur). Har biri o'z kutubxonalari bilan alohida o'rnatiladi va ishlaydi. Ikkala dasturga kerak bo'lgan `schemas` va `core` paketlari ikkala papkada aynan bir xil nusxada turadi (`local/packages`, `server/packages`), `scanner` esa faqat lokalda. Dasturlar bir-biriga ulanmaydi va bir-birining kodini import qilmaydi.

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
| **Blueprint (server A uchun)** | Skan → blueprint ko'rib chiqish | `blueprint.json` | Odam serverga yuklaydi, server saytga o'zi kiradi |
| **Bundle (server A' uchun)** | Skan → tadqiqot | `bundle.zip` | Odam serverga yuklaydi, server faqat yozadi va render qiladi |

**Server rejimlari:**
- **A** — blueprint + URL;
- **A'** — bundle (sayt ichki tarmoqda bo'lganda);
- **B** — faqat URL;
- **A+B** — blueprint asosiy, Razvedkachi bo'sh joylarni to'ldiradi.

Lokal dastur blueprint yoki bundle'ni **fayl sifatida** saqlaydi. Uni serverga **odam o'zi yuklaydi**: server veb-sahifasidagi ish yaratish formasi orqali. Lokal dastur serverga ulanmaydi va hech narsa yubormaydi.

## 4. Funksional talablar

### 4.0. Rollar va rol tanlash (FR-RL) — ikkala dasturda

- **FR-RL1. Rollarni topish.**
  - Lokal (kod bor): skaner rollarni koddan oladi — rol enum'lari va `choices`, guard'lar (`require_role("manager")`, `@permission_required`, `user.role == ...`), Django guruh va huquqlari, frontend'dagi rol tekshiruvlari (`<RequireRole role="manager">`), E2E testlardagi akkauntlar.
  - Server A rejimi: rollar yuklangan blueprint'da bor.
  - Server B rejimi (kod yo'q): rollar foydalanuvchi bergan test akkauntlaridan va saytdagi ochiq belgilardan (masalan, ro'yxatdan o'tishdagi "Men sotuvchiman / xaridorman" tanlovi) olinadi. Foydalanuvchi rol nomini va shu roldagi akkauntni qo'lda qo'sha oladi.
- **FR-RL2. Rollarni tasniflash.** Har bir rolga sababi bilan uchtadan biri beriladi:
  - `guest` — kirmagan mehmon;
  - `role` — bu rol uchun yo'riqnoma yozish mumkin;
  - `excluded` — administrator yoki adminga o'xshash rol, yoki noaniq rol (default-deny).

  Adminga o'xshash rol belgilari: superuser yoki staff bayrog'i; foydalanuvchilar, rollar yoki huquqlarni boshqarish; sayt sozlamalarini o'zgartirish; hamma yozuvlarga hech qanday cheklovsiz kirish; nomi `admin`, `administrator`, `superadmin`, `root` kabi. Sayt ishini bajaradigan xodim rollari (menejer, sotuv menejeri, operator, kuryer) bu belgilar bo'lmasa `role` hisoblanadi.
- **FR-RL3. Rol tanlash — variantlar.** Ishni boshlashda lokal va server veb-interfeysi topilgan rollarni kartalar (variantlar) ko'rinishida chiqaradi va so'raydi: "Saytda administratordan boshqa 4 ta rol topildi. Qaysi rol uchun yo'riqnoma yozay?" Har bir kartada:
  - rol nomi va qisqa tavsifi;
  - shu rolga ochiq sahifalar va vazifalar soni;
  - akkaunt kerakmi (vosita o'zi ro'yxatdan o'ta oladimi yoki sayt egasi berishi kerakmi).

  Bitta yoki bir nechta rol tanlanadi; har bir rol uchun **alohida** yo'riqnoma yoziladi. Chiqarib tashlangan rollar ham sababi bilan ko'rsatiladi, lekin ularni tanlab bo'lmaydi. Terminal buyruqlarida: `--list-roles` (variantlar ro'yxati) va `--role <id>`.
- **FR-RL4. Rol akkauntlari.** O'zi ro'yxatdan o'ta oladigan rol (odatda oddiy foydalanuvchi) uchun vosita o'zi ro'yxatdan o'tadi. Boshqa rollar uchun sayt egasi shu roldagi test akkauntlarini beradi (A, kerak bo'lsa B). Lokal 2- va 3-rejimda esa akkauntlarni vosita admin login orqali o'zi yaratadi va ish oxirida o'chiradi (FR-L13). Kirgandan keyin akkaunt haqiqatan tanlangan rolda ekani va admin yoki adminga o'xshash huquqi yo'qligi tekshiriladi (SEC-6). Akkaunt boshqa rolda yoki adminga o'xshash bo'lsa, ish to'xtaydi.

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
- **FR-S4. Route'larning rollari.** Har bir route uchun unga kira oladigan rollar (`guest` yoki bir yoki bir nechta `role`) yoki `excluded` belgilanadi va sababi yoziladi.
  - Faqat admin yoki adminga o'xshash rolga ochiq → `excluded`.
  - Rol tekshiruvi (`require_role("manager")`) → shu rol(lar).
  - Faqat kirish yoki egalik tekshiruvi → kira oladigan barcha `role`'lar.
  - Noaniq → `excluded`, hisobotga ham tushadi.
- **FR-S5. Obyektlar.** Har bir obyekt uchun:
  - amallar (CRUD va maxsus amallar);
  - statuslar;
  - har bir statusga **qaysi rollar yeta oladi** (`reachable_by`, rollar ro'yxati). Status faqat admin route'larida o'zgarsa — ro'yxat bo'sh.
- **FR-S6. Flow'lar.**
  - Har bir obyekt va amal juftligi alohida flow bo'ladi, hisob flow'lari ham qo'shiladi.
  - Har bir flow'ga `role`, `requires` va `stage` beriladi. Flow faqat `guest` yoki `role` turidagi rolga beriladi.
  - E2E testlardan olingan flow'lar ustun turadi.
- **FR-S7. Chiqish:**
  - `blueprint.json` (sxemaga mos);
  - `scan_report.md`: topilganlar, chiqarib tashlanganlar (sababi bilan) va noaniqlar.
- **FR-S8. Base URL** faqat parametrdan olinadi, hech qanday konfiguratsiya faylidan o'qilmaydi.

### 4.2. Tadqiqotchi — `core.explorer` (FR-E)

- **FR-E1. Kirish ma'lumotlari:**
  - blueprint va base URL;
  - muhit: `staging` yoki `production`;
  - maqsadli rol (FR-RL3);
  - maqsadli roldagi test akkauntlar — o'zi ro'yxatdan o'ta oladigan rolda ixtiyoriy (FR-RL4);
  - pochta adapteri: Mailpit yoki papka.
- **FR-E2. Akkauntlar.** Maqsadli roldagi ikkita test akkaunt (A, B), har biri alohida toza brauzer kontekstida. Faqat maqsadli rolning flow'lari bajariladi.
- **FR-E3. Flow'larni bajarish.**
  - Topologik tartibda bajariladi.
  - Har bir qadamdan keyin kutilgan natija tekshiriladi.
  - Natija: `verified`, `failed` yoki `skipped` — sababi bilan.
- **FR-E4. Test ma'lumoti generatori.** Validatsiya qoidalariga mos ma'lumot yaratadi (Faker va qoidalar), seed deterministik. Begona shaxs ma'lumotlari o'rniga qo'yiladigan to'qima qiymatlarni ham shu generator yaratadi: qiymat haqiqiy qiymatdan maxfiy kalit bilan hisoblanadi (HMAC), shuning uchun jadval saqlanmaydi (FR-E10).
- **FR-E5. Tasdiqlash.**
  - Email — pochta adapteri orqali.
  - SMS va boshqa kodlar — odam kiritadi: lokal yoki server UI'da, `manage.py` buyruqlarida terminalda.
- **FR-E6. Xavfli amallar** 5-bo'limdagi siyosat bo'yicha bajariladi.
- **FR-E7. Holatlar grafi.**
  - Xavfsiz elementlar bosiladi: tab, accordion, dropdown, modal ochuvchi tugmalar, filtrlar, sahifalash.
  - Takroriy holatlar DOM hash bo'yicha o'tkazib yuboriladi.
  - Chuqurlik va holatlar soniga limit qo'yiladi.
- **FR-E8. Yamalgan javob.** Maqsadli rol yeta olmaydigan (`reachable_by` da yo'q) statuslar shu usulda ko'rsatiladi. Rasmga `patched=true` belgisi qo'yiladi.
- **FR-E9. Har bir holat uchun yig'iladi:**
  - toza va SoM skrinshot (PNG);
  - elementlar: marker, role, name, bbox, selector;
  - aria snapshot;
  - URL, flow va qadam;
  - obyekt statusi;
  - tarmoq so'rovlari: metod, yo'l shabloni, status kodi. **So'rov tanasi yozilmaydi.**
- **FR-E10. Xiralashtirish va almashtirish.** Skrinshotlar maqsadli rolning o'z akkaunti bilan olinadi. Yo'riqnomaga uch xil narsa uch xil yo'l bilan kiradi:
  - **o'z holicha ko'rsatiladi** (xiralashtirilmaydi va almashtirilmaydi):
    - umumiy ma'lumotlar: sahifalar, menyular, tugmalar, matnlar, katalog, narxlar, ro'yxat va jadvallarning tuzilishi;
    - tashkilot ma'lumotlari: sayt nomi, sayt domenidagi email (masalan, `info@kun.uz`), rasmiy telefon, manzil, rekvizitlar;
    - nashr kontenti: sayt o'zi e'lon qilgan maqola va yangiliklar — matni, rasmlari, muallif imzosi — hamda reklama. Ularning ichidagi ism, telefon va email ham o'z holicha qoladi;
    - rolning test akkaunti kirganda ochiladigan o'z ma'lumotlari: o'z profili, o'zi yaratgan obyektlar;
  - **almashtiriladi:** begona shaxs ma'lumotlari — rol ularni ko'ra olsa ham (masalan, menejer ko'radigan mijozlarning ismi, telefoni, manzili). Ular rasmda ham, matnda ham FR-E4 generatori yaratgan, mavjud bo'lmagan test ma'lumotlari bilan almashtiriladi. Atrofi (jadval, ustunlar, status, tugmalar) aniq qoladi, xiralashtirish yo'q. Foydalanuvchi kontentida (boshqa odamning izohi, sharhi, xabari) muallif ismi va avatari bilan birga matnning o'zi ham to'qima matnga almashtiriladi, chunki uning ichida ism yoki telefon bo'lishi mumkin;
  - **xiralashtiriladi va matnga kirmaydi:** shu rolga tegishli bo'lmagan yoki u foydalana olmaydigan narsa (masalan, ekranda ko'rinib qolgan admin havolasi yoki boshqa rolning bo'limi).

  **Zona bo'yicha qaror.** Vosita avval shaxsga oid qiymatlarni topadi, keyin har birini u turgan zonaga qarab hal qiladi.
  - Qidiriladigan qiymatlar: email, telefon, karta raqami, pasport, JSHSHIR, manzil va ism. Ism faqat «Ism» yoki «F.I.Sh» yorlig'i yonidan emas, sahifa tuzilmasidan ham topiladi: muallif havolasi va imzosi (`/author/`, `rel=author`, `itemprop=author`), jadvalning «Ism», «F.I.Sh», «Mijoz» kabi ustunlari, `Person` belgisi, `Entity.pii_fields` maydonlari.
  - **Tashkilot** zonasi — o'z holicha: sayt domenidagi yoki uning subdomenidagi email; header, footer va navigatsiya; «Aloqa» va «Biz haqimizda» kabi sahifalar.
  - **Nashr** zonasi — o'z holicha: maqola yoki yangilik deb belgilangan sahifa (`article`, schema.org `Article`, `NewsArticle`) va reklama bloklari. Shart: bunday kontentni o'zi ro'yxatdan o'tgan har kim (`self_signup` rol) yarata olmasligi kerak. Aks holda u foydalanuvchi kontenti hisoblanadi.
  - **Foydalanuvchi kontenti** — almashtiriladi: izoh, sharh, e'lon, forum posti (schema.org `Comment`, `Review`; blueprint'da `self_signup` rol yaratadigan obyekt). Ochiq sahifada bo'lsa ham.
  - **Qolgan joylar** (rol kabinetidagi ro'yxat, jadval, tafsilot va h.k.) — test akkauntniki bo'lmasa almashtiriladi.
  - Zonani aniqlab bo'lmasa — begona (default-deny).

  Qo'shimcha qoidalar:
  - **barqaror almashtirish:** to'qima qiymat haqiqiy qiymatdan maxfiy kalit va ish id'si bilan hisoblanadi (HMAC). Bir xil haqiqiy qiymat ish davomida, ish to'xtab qayta boshlanganda ham, doim bir xil to'qima qiymat beradi, shuning uchun ro'yxat va tafsilot sahifalari bir-biriga mos keladi. Almashtirish jadvali kerak emas va saqlanmaydi. Bitta yozuvdagi (JSON obyekt, jadval qatori, kartochka) ism, telefon va email bitta to'qima odamdan olinadi. Kalit: lokalda `var/pseudonym.key`, serverda `YORIQNOMA_PSEUDONYM_KEY`; u capture, bundle, log va yo'riqnomaga tushmaydi;
  - begona haqiqiy qiymat faqat xotirada turadi; `capture.json`, rasmlar, loglar, `bundle.zip` va yo'riqnomaga yozilmaydi;
  - **rasm ichidagi matn** (rasm, canvas, fon rasmi, video kadri) OCR bilan o'qiladi va yuqoridagi zona qoidasi bo'yicha hal qilinadi. Begona yoki noaniq zonada uni almashtirib bo'lmaydi, shuning uchun faqat shu matn joyi xiralashtiriladi va hisobotga sababi bilan yoziladi. Begona odamning surati (profil rasmi, hujjat skani) neytral rasm bilan almashtiriladi;
  - noaniq qiymat (begonami, o'zinikimi yoki umumiymi — aniqlab bo'lmasa) begona deb hisoblanadi (default-deny);
  - umumiy deb qoldirilgan qiymatlar (tashkilot va nashr) `CaptureRun.public_values` ga yoziladi: yakuniy tekshiruv va LLM matnini tekshirish ularni begona deb hisoblamaydi;
  - hisobotda har bir holat uchun topilgan, o'z holicha qoldirilgan, almashtirilgan va xiralashtirilgan qiymatlar soni zonasi bilan ko'rsatiladi (begona qiymatlarning o'zisiz);
  - egasi bergan test akkauntning o'z ma'lumotlari o'z holicha ko'rsatiladi, shuning uchun test akkauntga haqiqiy odamning ma'lumotlarini yozmaslik kerak (bu ogohlantirish akkaunt formasida ko'rsatiladi).
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

  Yo'riqnoma boshida qaysi rol uchun yozilgani va bu rolni kim beradi (masalan, «Sotuv menejeri» rolini sayt administratori beradi) aytiladi.
- **FR-W5. Faqat tasdiqlangan flow'lar.** Yo'riqnomaga faqat `verified` flow'lar kiradi. `failed` flow'lar "Tekshirilmagan" ilovasiga tushadi.
- **FR-W6. Qamrov hisoboti.**
  - Foiz hisoblanadi: maqsadli rol yo'llari, formalar, tugmalar, amallar, statuslar bo'yicha.
  - Qamralmaganlar ro'yxati sababi bilan chiqariladi.
- **FR-W7. Kesh.** Bir xil kirish (holat hash + prompt versiyasi + model) uchun LLM qayta chaqirilmaydi. Kesh fayllarda saqlanadi.

### 4.4. Renderer — `core.render` (FR-R)

- **FR-R1. Yo'riqnoma rasmlari** modelga berilgan rasmdan alohida chiziladi (Pillow):
  - maqsad atrofida qirqim;
  - spotlight;
  - raqamli belgilar;
  - strelka;
  - xiralashtirish faqat FR-E10 bo'yicha: maqsadli rol ko'radigan narsa aniq qoladi.
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
  - rejim (FR-L13): kod + link, kod + link + admin login, yoki link + admin login;
  - kod papkasining yo'li (1- va 2-rejimda majburiy, 3-rejimda yo'q);
  - admin login, paroli (Fernet bilan shifrlangan) va admin panel manzili (2- va 3-rejimda; manzil ixtiyoriy);
  - base URL va muhit (staging yoki production);
  - test akkauntlar — rol bo'yicha (FR-RL4);
  - pochta adapteri (Mailpit URL yoki papka) — ixtiyoriy;
  - til.
- **FR-L4. Rol va natija turini tanlash.** Har bir ishni boshlashda foydalanuvchi maqsadli rol(lar)ni variantlardan tanlaydi (FR-RL3) va uchta natija turidan birini tanlaydi:
  - **To'liq yo'riqnoma** — skan → blueprint ko'rib chiqish → tadqiqot → yozish (Ollama) → render (HTML, PDF, DOCX);
  - **Blueprint (server A uchun)** — skan → ko'rib chiqish → `blueprint.json` (3-rejimda yo'q: u yerda blueprint faqat ish davomida saytdan o'rganiladi va ish natijalarida chiqadi);
  - **Bundle (server A' uchun)** — skan → ko'rib chiqish → tadqiqot → `bundle.zip`.
- **FR-L5. Blueprint ko'rib chiqish.** Skandan keyin foydalanuvchi quyidagilarni ko'radi va o'zgartira oladi:
  - rollar (tasnifi va sababi bilan), sahifalar, obyektlar va flow'lar ro'yxati;
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
- **FR-L9. Server uchun fayl.** "Blueprint" va "Bundle" natijalari ish sahifasidan yuklab olinadi (`blueprint.json`, `bundle.zip`) va natija papkasida saqlanadi. Sahifada qisqa ko'rsatma bor: "Bu faylni server sahifasidagi «Yangi ish» formasida yuklang". Lokal dastur serverga ulanmaydi, server manzili yoki kalitini so'ramaydi va saqlamaydi.
- **FR-L10. Boshqaruv buyruqlari** (avtomatlashtirish va CI uchun):

  ```
  manage.py scan | explore | write | render | run --output full|blueprint|bundle | bundle | cleanup --run <id> | eval
  ```

  Ular UI bilan bir xil servislarni chaqiradi.
- **FR-L11. Ishga tushish tekshiruvlari.** Ollama ishlayaptimi, model bormi, Playwright chromium o'rnatilganmi, base URL ochiladimi — har biri uchun aniq o'zbekcha yechim xabari chiqariladi.
- **FR-L13. Uch rejim (loyiha yaratishda tanlanadi).** Lokal dastur bitta; foydalanuvchi «Sizda nima bor?» savoliga javob beradi va faqat shu rejimga kerakli ma'lumotni kiritadi:

  | Rejim | Kiritiladi | Rollar | Test akkauntlar |
  |---|---|---|---|
  | 1. Kod + sayt linki | kod papkasi yo'li, URL | koddan | o'zi ro'yxatdan o'tadi yoki sayt egasi beradi |
  | 2. Kod + sayt linki + admin login | kod papkasi yo'li, URL, admin login va paroli, admin panel manzili (ixtiyoriy) | koddan; admin panelidagi rol bilan moslanadi | admin panelida vosita yaratadi |
  | 3. Sayt linki + admin login | URL, admin login va paroli, admin panel manzili (ixtiyoriy) | admin panelining «yangi foydalanuvchi» formasidan | admin panelida vosita yaratadi |

  - «Tekshirish» tugmasi: kod skanerlanadi (1, 2) va admin paneliga kirib rollar o'qiladi (2, 3). Keyin rol variantlardan tanlanadi (FR-RL3), so'ng ish boshlanadi.
  - 3-rejimda sahifa, forma va vazifalar ish boshida saytning o'zidan o'rganiladi (serverning B rejimi bilan bir xil razvedka, LLM — Ollama).
  - Admin login faqat test foydalanuvchilarni yaratish va o'chirish uchun (SEC-18). Ish tugagach — muvaffaqiyatli, xato yoki bekor qilingan bo'lsa ham — vosita yaratgan foydalanuvchilar va ular yaratgan obyektlar o'chiriladi. O'chmagani ish sahifasida ko'rsatiladi, «Tozalashni qayta urinish» tugmasi va `manage.py cleanup --run <id>` bor.
  - Admin panel manzili ixtiyoriy: bo'sh qolsa, vosita odatiy manzillarni (`/admin/`, `/dashboard`, `/panel` ...) sinaydi, so'ng admin sifatida saytga kirib uning havolalaridan panelni topadi. Pochta (papka yoki Mailpit) ham ixtiyoriy: u faqat sayt ro'yxatdan o'tishda email tasdiqlashni so'rasa kerak.
  - Qo'llab-quvvatlanadigan admin panellar: Django admin (aniq qadamlar), «yangi foydalanuvchi» formasi va o'chirish tugmasi bor oddiy panel; boshqalarida Ollama agenti xuddi shu cheklovlar ichida ishlaydi.

- **FR-L12. `eval` — modellarni solishtirish.** Oltin to'plamda ikki modelni solishtiradi:
  - sxema xatolari;
  - marker xatolari;
  - vaqt;
  - qo'lda baholash uchun yonma-yon sahifa.

### 4.6. Server dastur — Django (FR-SV)

- **FR-SV1. Rejimlar:** A, A', B, A+B.
- **FR-SV2. Veb-interfeys** (Django shablonlar + HTMX):
  - server foydalanuvchilari uchun ro'yxatdan o'tish va kirish (Django auth);
  - domen qo'shish va tasdiqlash;
  - ish yaratish: rol tanlash (variantlar, FR-RL3) va A, A' rejimlarida lokal dastur yaratgan faylni yuklash;
  - jarayonni jonli kuzatish (HTMX polling);
  - SMS kodini kiritish;
  - natijalarni yuklab olish.
- **FR-SV3. REST API** (DRF) — ARCHITECTURE §7.4 da. Faqat sessiya (login) bilan autentifikatsiya qilinadi; API kalitlar yo'q.
- **FR-SV4. Navbat.** Celery + Redis, worker'lar va Celery beat (davriy vazifalar). Bir vaqtdagi ishlar soni konfiguratsiyada belgilanadi.
- **FR-SV5. Razvedkachi (B rejimi):**
  - preflight;
  - mehmon sifatida aylanish (guest crawl);
  - ochiq JS bundle'lardan route'lar;
  - tarmoq kuzatuvi;
  - kirish yoki ro'yxatdan o'tish;
  - imtiyoz tekshiruvi;
  - rollarni aniqlash: berilgan akkauntlar va saytdagi belgilardan (FR-RL1);
  - Claude agenti (tool use);
  - validatsiyani o'rganish.

  Natija: `blueprint.json` (`source=discovered`, `confidence` bilan).
- **FR-SV6. Claude modellari va xarajat.**
  - `claude-haiku-5-5` — tasniflash;
  - `claude-sonnet-5-5` — agent va tavsiflar;
  - `claude-opus-5-5` — yakuniy tekshiruv.
  - Structured outputs (`messages.parse`) va prompt caching ishlatiladi.
  - Har bir ish uchun token va narx hisoblanadi, byudjet limiti bor.
  - Umumiy xarajat ham cheklanadi, chunki ro'yxatdan o'tish hammaga ochiq va barcha ishlar bitta Claude kaliti hisobidan to'lanadi:
    - har bir foydalanuvchi uchun kunlik va oylik limit;
    - butun server uchun oylik limit.

    Limitlar konfiguratsiyada belgilanadi. Limitga yetilganda yangi ish yaratilmaydi va foydalanuvchiga sababi ko'rsatiladi.
- **FR-SV7. Saqlash muddati.** Natijalar konfiguratsiyadagi muddat (standart 30 kun) o'tgach o'chiriladi.
- **FR-SV8. Django admin.** Server operatorlari uchun `/ops/` yo'lida joylashadi (`/admin/` emas) va faqat staff'ga ochiq.
- **FR-SV9. Lokal dastur faylini qabul qilish.** Foydalanuvchi login qilib, `/jobs/new/` formasida `blueprint.json` (A rejimi) yoki `bundle.zip` (A' rejimi) faylini o'zi yuklaydi. Fayl sxema va SEC-13 bo'yicha tekshiriladi. Lokal dasturdan avtomatik qabul qilish yo'li yo'q.

## 5. Xavfsizlik talablari (SEC)

- **SEC-1. Default-deny** — barcha komponentlarda.
- **SEC-2. Admin yo'q.** Administrator va adminga o'xshash rollarning yo'llari va huquqlari hech qachon olinmaydi va ko'rsatilmaydi (lokal 2- va 3-rejimdagi test foydalanuvchi yaratish bundan mustasno, u ham faqat SEC-18 bo'yicha). Begona shaxslarning haqiqiy ma'lumotlari yo'riqnomaga kirmaydi: ular to'qima test ma'lumotlari bilan almashtiriladi (FR-E10).
- **SEC-3. Skaner chegaralari.**
  - Fayllar faqat `SafeFS` orqali o'qiladi.
  - **O'qilmaydigan fayllar:** `.env*`, `*.pem`, `*.key`, `*.p12`, `*.sql`, `*.db`, `*.sqlite*`, `*dump*`, `docker-compose*.yml`, `secrets*`, `storage/`, `uploads/`, `logs/`, `node_modules/`, `.git/`, `venv/`, `.venv/`.
  - Skaner va core'da DB drayverlari yo'q, bu test bilan tekshiriladi.
- **SEC-4. Tarmoq firewall'i (Tadqiqotchi).**
  - `deny_paths` ga tushgan so'rovlar bekor qilinadi.
  - Boshqa domenlar: faqat statik resurslar uchun GET'ga ruxsat (stylesheet, script, font, image). Boshqa domenga xhr/fetch, navigatsiya va GET bo'lmagan so'rovlar bekor qilinadi.
  - Test akkauntlar o'zi yaratmagan obyektga DELETE, PUT yoki PATCH bekor qilinadi.
  - Barcha bloklangan so'rovlar logga yoziladi.
- **SEC-5. Xavfli amallar.**
  - O'chirish, bekor qilish, tahrirlash va status o'zgartirish faqat test akkauntlar o'zi yaratgan obyektlarda. Menejer kabi rollar boshqalarning yozuvlarini ko'ra olsa ham, ularni o'zgartirmaydi: kerakli obyektlar avval yordamchi test akkauntda (masalan, test mijoz) yaratiladi va maqsadli rol faqat shular ustida ishlaydi.
  - **Production:** faqat tasdiqlash oynasigacha.
  - **To'lov:** faqat sandbox.
  - **Hisobni o'chirish:** eng oxirida va faqat test akkauntda.
- **SEC-6. Imtiyoz tekshiruvi.** Kirgandan keyin alohida "probe" sahifasida tekshiriladi. Bu sahifada capture o'chirilgan, firewall faqat probe so'rovlariga ruxsat beradi.
  - Admin API'larga yuborilgan so'rov 401, 403 yoki 404 qaytarishi kutiladi.
  - `/admin` sahifasi login'ga qaytarishi yoki 403 ko'rsatishi kutiladi.
  - Admin kontenti ochilsa, ish **to'xtatiladi**.
  - Akkaunt tanlangan rolda bo'lmasa yoki adminga o'xshash huquqi topilsa (foydalanuvchilar, rollar yoki sozlamalarni boshqarish sahifalari ochilsa), ish to'xtatiladi.
  - Natija faqat "ha/yo'q" ko'rinishida saqlanadi, sahifa mazmuni saqlanmaydi.
- **SEC-7. Almashtirish.**
  - Begona shaxs ma'lumotlari skrinshot olinishidan oldin to'qima test ma'lumotlari bilan almashtiriladi (FR-E10); tashkilot va nashr ma'lumotlari, vosita yaratgan va test akkauntning o'z ma'lumotlari almashtirilmaydi.
  - Claude'ga (va Ollama'ga) faqat almashtirish va OCR tekshiruvidan o'tgan rasm va matn beriladi. Yuborishdan oldin matn yana tekshiriladi: test qiymatlari va umumiy qiymatlardan (`public_values`) boshqa shaxsiy ma'lumot topilsa, u yuborilmaydi.
  - Almashtirish jadvali saqlanmaydi: to'qima qiymat HMAC bilan qayta hisoblanadi. HMAC kaliti git'ga, capture'ga, bundle'ga va loglarga tushmaydi.
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
- **SEC-12. Sirlar.**
  - Test akkaunt parollari Fernet bilan shifrlanadi, ish tugagach o'chiriladi, loglarda maskalanadi.
  - **Claude API kaliti** (`ANTHROPIC_API_KEY`) faqat serverning o'zidagi env faylda turadi va faqat Claude'ni chaqiradigan konteynerga (Celery worker) beriladi. Web, beat va boshqa servislarga berilmaydi.
  - Kalit kodda, bazada, loglarda, xato xabarlarida va veb-interfeysda hech qachon ko'rinmaydi. Log filtri `x-api-key` sarlavhasini va `sk-ant-` bilan boshlanadigan qiymatlarni ham maskalaydi.
  - Kalit bo'lmasa worker ishga tushmaydi va aniq xabar chiqaradi (birinchi ishgacha kutilmaydi).
  - Env fayllar git'ga tushmaydi (`.env`, `.env.*`, `*.env`). Repoda faqat qiymatsiz shablonlar (`*.example`) turadi.
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
  - Har kim faqat o'z domenlari va ishlarini ko'radi.
  - Parollar argon2 bilan saqlanadi (Django `Argon2PasswordHasher`).
- **SEC-16. Lokal dastur.**
  - Faqat `127.0.0.1` da tinglaydi, `ALLOWED_HOSTS` = `localhost`, `127.0.0.1`.
  - CSRF yoqilgan.
  - Kod papkasi yo'li faqat foydalanuvchi o'zi tanlagan papkadan olinadi va `SafeFS` orqali o'qiladi.
- **SEC-17. Server Django sozlamalari.**
  - `DEBUG=False`, `SECURE_*` sozlamalari (HSTS, SSL redirect, secure cookie).
  - `X-Frame-Options`, CSP (django-csp).
  - Login urinishlari cheklanadi (django-axes yoki rate limit).
  - `manage.py check --deploy` toza o'tishi kerak.

- **SEC-18. Admin login (lokal 2- va 3-rejim).**
  - Faqat lokal dasturda; serverga berilmaydi. Parol Fernet bilan shifrlanadi.
  - Admin sessiyasi alohida brauzer kontekstida: capture, skrinshot va log'ga sahifa mazmuni yozilmaydi; admin sahifalari blueprint, capture va yo'riqnomaga kirmaydi.
  - Admin sessiyasining firewall'i (`ProvisionGuard`): o'qish (GET) mumkin; yozish faqat (1) admin paneliga kirish, (2) foydalanuvchiga o'xshash to'plamga yangi yozuv qo'shish, (3) vosita shu ishda yaratgan (model, id) juftligini o'zgartirish yoki o'chirish uchun. Ro'yxatdagi ommaviy amallar, sozlamalar, rollar, huquqlar, boshqalarning yozuvlari va tizimdan chiqish bloklanadi va logga yoziladi.
  - Yaratilgan foydalanuvchi faqat tanlangan rolda bo'ladi; staff va superuser belgilari o'chiq. Adminga o'xshash rol uchun foydalanuvchi yaratilmaydi. Kirgandan keyin SEC-6 tekshiruvi baribir bajariladi.
  - Ish oxirida tozalash majburiy; ro'yxat `provision.json` da (parolsiz) saqlanadi, shuning uchun to'xtab qolgan ishdan keyin ham tozalash mumkin.

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
- **Bitta ishning papkasi** (lokalda `local/var/runs/`, serverda MinIO'da xuddi shu tuzilma):

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
- B rejimi faqat sayt orqali ko'rinadigan va topiladigan funksiyalarni qamraydi. Rollar faqat berilgan akkauntlar va saytda ko'rinadigan belgilar orqali aniqlanadi.
- Admin harakati talab qiladigan holatlar yamalgan javob yoki matn orqali ko'rsatiladi.
- Server-rendered saytlar ham qo'llab-quvvatlanadi, chunki Tadqiqotchi DOM bilan ishlaydi.
- Lokal 2- va 3-rejim: admin paneli Django admin yoki «yangi foydalanuvchi» formasi bor oddiy panel bo'lsa aniq ishlaydi; boshqa panellarda Ollama agenti ishlaydi va natija kafolatlanmagan. Captcha yoki ikki bosqichli kirish bo'lgan admin panelida vosita kira olmaydi.
- Lokal 2- va 3-rejimda production sayt tanlansa ham test foydalanuvchilar haqiqiy saytda yaratiladi (ish oxirida o'chiriladi); staging tavsiya etiladi.
- Server B rejimida akkaunt berilmasa, vosita saytda o'zi ro'yxatdan o'tadi; bu faqat ro'yxatdan o'tgan har kim oladigan rol uchun to'g'ri. Xodim rollari uchun shu roldagi akkaunt berilishi kerak.
- Mobil ilovalar va desktop dasturlar doiradan tashqari.

## 9. Qabul qilish mezonlari (demo_shop poligonida)

- **QM-1. Skaner:**
  - admindan boshqa barcha rollar topiladi va to'g'ri tasniflanadi (demo_shop: `customer`, `manager`, `courier` — `role`; `admin` — `excluded`);
  - har bir rol yo'llarining 100% topiladi;
  - admin yo'llari 0 ta;
  - `.env` fayli ochilmagani testda isbotlangan.
- **QM-2. Tadqiqotchi:**
  - har bir tanlangan rol uchun flow'larning ≥ 90% `verified`;
  - admin so'rovlari 0 ta (firewall logi bo'yicha);
  - begona obyektga DELETE 0 ta.
- **QM-3. Yo'riqnoma:**
  - 9 bo'lim mavjud;
  - qamrov ≥ 90%;
  - marker xatolari 0 ta;
  - natijada begona shaxslarning haqiqiy ma'lumotlari topilmaydi (regex skaner bilan; test ma'lumotlari va `public_values` bundan mustasno). demo_shop'da: menejer yo'riqnomasi, `capture.json` va `bundle.zip` ichida seed'dagi boshqa mijozning ismi, emaili va telefoni yo'q, ularning o'rnida to'qima qiymatlar turadi;
  - demo_shop'da: footer'dagi do'konning o'z emaili va telefoni o'z holicha qoladi; mahsulot sahifasidagi boshqa mijozlar sharhlari (ism va matn) to'qima qiymatlar bilan almashtiriladi; boshqa mijoz buyurtmasiga ilova qilingan rasm ichidagi ism va telefon (OCR) xiralashtiriladi;
  - ish o'rtada to'xtatilib qayta boshlansa, to'qima qiymatlar o'zgarmaydi;
  - maqsadli rol ko'radigan elementlar xiralashtirilmagan, boshqa rol va admin elementlari matnda yo'q.
- **QM-4. Lokal dastur:**
  - UI orqali rol variantlari chiqadi va tanlangan rol uchun "To'liq yo'riqnoma" Ollama bilan internetsiz boshidan oxirigacha ishlaydi;
  - "Blueprint" va "Bundle" natijalari server sxemasidan o'tadi;
  - lokal dastur serverga hech qanday so'rov yubormaydi; uning fayllari server veb-formasi orqali yuklanib, ish yaratiladi.
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
| F8 | Lokal dastur: uch rejim, admin orqali test foydalanuvchilar va tozalash |

Batafsil vazifalar: `docs/TASKS.md`.
