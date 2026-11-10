# Lokal dastur: internetsiz o'rnatish to'plami

Bu papkada lokal dastur (`local/`) boshqa kompyuterda **internetsiz** o'rnatilishi va ishlashi
uchun kerak bo'lgan hamma narsa bor. Hajmi taxminan 20 GB, uning 17,4 GB i `gemma4:26b` modeli.

Faqat asosiy model `gemma4:26b` olingan. Muqobil `qwen3.6:27b` (16,8 GB) bu to'plamga kirmaydi:
dastur unga muhtoj emas, faqat `manage.py eval` (modellarni solishtirish) uni standart ro'yxatda
chaqiradi. Kerak bo'lsa, `eval --models gemma4:26b` deb ishlating.

Mo'ljallangan kompyuter: Windows 10/11, 64-bit (x64).

## Tarkib

| Papka yoki fayl | Nima | Hajmi |
|---|---|---|
| `wheels/` | 80 ta `.whl` paket: `local/uv.lock` dagi barcha kutubxonalar (dasturning o'zi, testlar va dev vositalari), hamda build uchun `hatchling` va `editables`. Hammasi Windows x64, Python 3.12 uchun. Har birining sha256 hashi `uv.lock` bilan tekshirilgan | 181 MB |
| `requirements.txt` | `uv.lock` dan olingan aniq versiyalar ro'yxati | — |
| `python/` | Python 3.12.16, uv o'rnatadigan arxiv (python-build-standalone) | 21 MB |
| `uv/` | `uv.exe` 0.13.7 (hamda `uvx.exe`, `uvw.exe`) | 31 MB |
| `playwright/ms-playwright/` | Chromium 1248, headless shell, ffmpeg, winldd (Playwright 1.64.1 uchun) | 718 MB |
| `ollama/OllamaSetup.exe` | Ollama 0.40.15 o'rnatuvchisi | 1,6 GB |
| `ollama/models/` | `gemma4:26b` modeli (vision bilan): asosiy model, projector va draft fayllari, manifest va metadata | 17,4 GB |
| `vcredist/vc_redist.x64.exe` | Microsoft Visual C++ runtime (onnxruntime va opencv uchun; Windows'da yo'q bo'lsa o'rnatiladi) | 24 MB |
| `install_offline.bat` | Yangi kompyuterda bir marta: hammasini o'rnatadi | — |
| `start_offline.bat` | Dasturni internetsiz ishga tushiradi | — |
| `tayyorlash.bat`, `tools/` | Bu papkani yangilash (internet bor kompyuterda) | — |

## Yangi kompyuterga o'rnatish

1. Loyiha papkasini butunligicha fleshkaga, keyin yangi kompyuterga ko'chiring. `packets` papkasi
   `local` papkasi bilan yonma-yon turishi kerak (loyiha ildizida). `local/.venv` ni ko'chirish shart emas.
2. `packets\lokal\install_offline.bat` ni ikki marta bosing. U quyidagilarni bajaradi:
   1. `uv` ni `%USERPROFILE%\.local\bin` ga qo'yadi (uv kompyuterda bo'lmasa);
   2. Python 3.12 ni `python/` dagi arxivdan o'rnatadi (kompyuterda bo'lmasa);
   3. Visual C++ runtime'ni o'rnatadi (yo'q bo'lsa; Windows ruxsat so'rashi mumkin);
   4. `local\.venv` ni yaratadi va barcha kutubxonalarni `wheels/` dan o'rnatadi, keyin
      `uv sync` internetsiz o'tishini tekshiradi;
   5. Chromium'ni `%LOCALAPPDATA%\ms-playwright` ga ko'chiradi;
   6. Ollama'ni o'rnatadi (yo'q bo'lsa) va modellarni `%USERPROFILE%\.ollama\models` ga ko'chiradi
      (`OLLAMA_MODELS` o'rnatilgan bo'lsa, o'sha papkaga). Fleshkadan 5–15 daqiqa ketadi.

   Parametrlar: `--no-models` modelni ko'chirmaydi, `--no-ollama` esa Ollama'ni ham o'rnatmaydi
   (masalan, ular allaqachon bor bo'lsa).
3. Dasturni `packets\lokal\start_offline.bat` bilan ishga tushiring. U `local\startup.bat` ni
   internetsiz rejimda chaqiradi (`UV_OFFLINE=1`) va dastur `http://127.0.0.1:8765` da ochiladi.
   O'rnatishdan keyin odatdagi `local\startup.bat` ham ishlaydi.

Skriptni qayta ishga tushirish xavfsiz: bori o'tkazib yuboriladi.

## Qanday tekshirilgan

Bu kompyuterda loyihaning toza nusxasida sinaldi: uv keshi bo'sh, Python o'rnatilmagan va
`UV_OFFLINE=1` (internet o'chirilgan) holatda.

- `install_offline.bat` xatosiz o'tdi (11 s, modellardan tashqari): Python `python/` dan o'rnatildi,
  81 ta paket `wheels/` dan o'rnatildi, `uv sync` internetsiz o'tdi va `uv.lock` o'zgarmadi.
- Qwen olib tashlangach, Ollama `ollama/models/` papkasidan `gemma4:26b` ni ko'rdi (`ollama list`,
  `ollama show`: vision bor). Fayllarning sha256 hashlari manifest bilan mos.
- `startup.bat` dasturni ishga tushirdi. Ishga tushish tekshiruvlari (bu kompyuterning Ollama'sida): Ollama ishlayapti, 2 ta model
  topildi, «gemma4:26b» rasmlarni ko'radi, Chromium o'rnatilgan. Bosh sahifa 200 qaytardi.
- `manage.py check` toza o'tdi, OCR (RapidOCR) yuklandi, Chromium sahifa ochdi.
- Tezkor testlar: 262 ta o'tdi. Bitta test yiqildi, lekin paketlar sababli emas: u repo ildizidagi
  `docs/` papkasini o'qiydi, sinov nusxasida esa faqat `local/` bor edi.

## Yangilash (`local/uv.lock` o'zgarganda)

Kutubxonalar o'zgarsa, `install_offline.bat` "uv sync internetsiz o'tmadi" deydi. Unda internet bor
kompyuterda `tayyorlash.bat` ni ishga tushiring. U:

1. `requirements.txt` ni qayta chiqaradi;
2. `wheels/` ni tozalab, `.whl` larni `uv.lock` dagi havolalardan yuklaydi va hashini tekshiradi;
3. Chromium'ni Playwright'ning yangi versiyasiga moslab yangilaydi.

**Qo'lda yangilash** kerak bo'lganlar:

- **Ollama modellari:** `ollama pull <model>`, keyin `%USERPROFILE%\.ollama\models` ni
  `ollama/models/` ga ko'chiring.
- **Ollama o'rnatuvchisi:** yangi `OllamaSetup.exe` ni `ollama/` ga qo'ying.
- **uv:** yangi `uv.exe` ni `uv/` ga qo'ying. Python arxivi uv versiyasiga bog'liq. Kerakli manzil
  `uv python list 3.12 --output-format json` dagi `url` maydonida turadi. Arxivni
  `python/<sana>/<fayl nomi>` ko'rinishida saqlang: `%2B` o'rniga `+` yozing.

## Bu to'plamga kirmaganlar

- **Node.js:** faqat poligonning React qismini qayta build qilish uchun kerak. Build qilingan
  `web/dist` repoda bor, shuning uchun dastur va testlar Node'siz ishlaydi.
- **pre-commit hook'lari:** `pre-commit install` hook'larni GitHub'dan yuklaydi. Bu ixtiyoriy dev
  vositasi, ruff va mypy esa `wheels/` da bor.
- **Linux uchun paketlar:** bu yerdagi `.whl` lar faqat Windows x64 uchun.
