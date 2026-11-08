# Server dasturini o'rnatish (deploy)

Bu hujjat `server/` dasturini Linux serverga Docker Compose bilan o'rnatishni tushuntiradi. Talablar: `docs/TZ.md` (4.6, 5-bo'lim), tuzilma: `docs/ARCHITECTURE.md` §7.

Lokal dastur bu serverga ulanmaydi. Uning fayllarini (`blueprint.json`, `bundle.zip`) foydalanuvchi o'zi server sahifasidagi «Yangi ish» formasida yuklaydi.

## 1. Kerakli narsalar

- Linux server (Ubuntu 24.04 tavsiya): 4 CPU, 8 GB RAM, 80 GB disk. Har bir parallel ish taxminan 1–2 GB RAM oladi.
- Docker Engine 27+ va Compose v2.
- Domen. Misol uchun `yoriqnoma.example.uz`.
- DNS yozuvlari:

  | Yozuv | Qiymat | Nima uchun |
  |---|---|---|
  | `A yoriqnoma.example.uz` | server IP | sayt (Caddy, TLS) |
  | `A files.yoriqnoma.example.uz` | server IP | natijalarni yuklab olish havolalari (MinIO) |
  | `MX inbox.yoriqnoma.example.uz` | `yoriqnoma.example.uz` (10) | test pochta: `*@inbox.yoriqnoma.example.uz` Mailpit'ga tushadi |

- Ochiq portlar: 80, 443 (Caddy) va 25 (Mailpit SMTP, test xatlari uchun). Boshqa hech qaysi port ochilmaydi.

## 2. O'rnatish

```bash
git clone <repo> /opt/yoriqnoma
cd /opt/yoriqnoma/server
cp docker/.env.example docker/.env
cp docker/worker.env.example docker/worker.env
chmod 600 docker/.env docker/worker.env
```

`docker/.env` ni to'ldiring:

- `DJANGO_SECRET_KEY` — uzun tasodifiy qiymat: `openssl rand -base64 48`.
- `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `YORIQNOMA_PUBLIC_HOST`, `YORIQNOMA_PUBLIC_URL` — domeningiz.
- `POSTGRES_PASSWORD` va unga mos `DATABASE_URL`.
- `S3_ACCESS_KEY`, `S3_SECRET_KEY` — MinIO uchun yangi, tasodifiy qiymatlar. `S3_PUBLIC_ENDPOINT_URL=https://files.<domen>`.
- `YORIQNOMA_FERNET_KEY` — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `YORIQNOMA_PSEUDONYM_KEY` — begona shaxs ma'lumotini almashtirish kaliti (TZ FR-E10): `openssl rand -base64 48`. **Uni o'zgartirmang**: o'zgarsa, yangilangan yo'riqnomalardagi to'qima ismlar boshqacha chiqadi.
- `YORIQNOMA_MAIL_DOMAIN=inbox.<domen>`.
- Xarajat limitlari (TZ FR-SV6): `YORIQNOMA_USER_DAILY_BUDGET_USD`, `YORIQNOMA_USER_MONTHLY_BUDGET_USD`, `YORIQNOMA_MONTHLY_BUDGET_USD`, `YORIQNOMA_MAX_JOB_BUDGET_USD`.

`docker/worker.env` ga faqat Claude kalitini yozing (6-bo'lim).

Ishga tushirish:

```bash
docker compose -f docker/compose.yml up -d --build
sudo sh docker/egress-firewall.sh
docker compose -f docker/compose.yml exec web python manage.py createsuperuser
docker compose -f docker/compose.yml exec web python manage.py check --deploy
```

- Operatorlar paneli `https://<domen>/ops/` da (faqat staff). `/admin/` yo'li yo'q.
- `manage.py` buyruqlari faqat konteyner ichida ishlaydi (`docker compose exec web ...`): Django env faylni o'zi o'qimaydi, qiymatlarni compose beradi.

## 3. Worker va tarmoq cheklovlari (TZ SEC-10, SEC-11)

Worker saytlarga brauzer bilan kiradi, shuning uchun u server ichki tarmog'iga yeta olmasligi kerak. Himoya uch qavat:

1. **Ish yaratishda.** Ish URL'i `url_guard` dan o'tadi: faqat `http` va `https`, hostning barcha DNS javoblari ommaviy manzil bo'lishi kerak.
2. **Brauzerning har bir so'rovi.** Core firewall'i har bir so'rov hostini qayta tekshiradi (`HostGuard`). Bu sayt o'zi, redirect'lar, boshqa domendagi rasm, websocket — hammasiga tegishli. Serverning o'z HTTP so'rovlari (domen tasdiqlash, `robots.txt`, sitemap, JS fayllar) DNS'ni bir marta hal qilib, aynan tekshirilgan manzilga ulanadi (DNS pinning).
3. **Tarmoq darajasi.** Worker internetga faqat `egress` tarmog'i (`172.30.0.0/24`) orqali chiqadi. `docker/egress-firewall.sh` `DOCKER-USER` zanjiriga shu tarmoqdan xususiy, loopback, link-local (bulut metadata `169.254.169.254`) va boshqa maxsus diapazonlarga boradigan paketlarni tashlab yuboradigan qoidalarni qo'shadi. PostgreSQL, Redis, MinIO va Mailpit bilan worker alohida `internal` tarmoq orqali gaplashadi (u `internal: true`, ya'ni internetga chiqmaydi), shuning uchun bu qoidalar ularga tegmaydi.

Bu yondashuv tanlandi, chunki u eng sodda: alohida egress-proxy servisi kerak emas.

Qoidalar server qayta yuklanganda yo'qoladi. Ularni har safar ishga tushirish uchun systemd unit qo'ying:

```ini
# /etc/systemd/system/yoriqnoma-egress.service
[Unit]
Description=Yoriqnoma worker egress rules
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/bin/sh /opt/yoriqnoma/server/docker/egress-firewall.sh

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now yoriqnoma-egress
```

**Izolyatsiya.** Worker root'siz foydalanuvchi (`pwuser`) bilan ishlaydi:

- `cap_drop: ALL`, `no-new-privileges`;
- RAM limiti `mem_limit: 4g`, CPU limiti `cpus: 2`;
- vaqt limiti: `YORIQNOMA_JOB_TIME_LIMIT_S`, osilib qolgan ishlarni beat har 10 daqiqada to'xtatadi.

Har bir ish alohida yangi jarayonda ishlaydi (`--max-tasks-per-child=1`): har safar yangi Python va yangi brauzer. Alohida konteyner esa har bir ish uchun emas, bitta worker konteyneri uchun ochiladi. Bir vaqtda nechta ish ishlashini `YORIQNOMA_MAX_CONCURRENT_JOBS` belgilaydi.

## 4. Zaxira nusxa

- **PostgreSQL** — har kuni:

  ```bash
  docker compose -f docker/compose.yml exec -T postgres pg_dump -U yoriqnoma yoriqnoma | gzip > /backup/db-$(date +%F).sql.gz
  ```

- **MinIO** (natijalar, yuklangan fayllar) — `minio-data` volume'ini nusxalang yoki `mc mirror` ishlating. Natijalar baribir `YORIQNOMA_RETENTION_DAYS` kundan keyin o'chadi, shuning uchun eng muhimi bazadir.
- `docker/.env` va `docker/worker.env` — alohida, shifrlangan joyda saqlang. Ular gitda yo'q.

## 5. Yangilash

```bash
cd /opt/yoriqnoma && git pull
cd server
docker compose -f docker/compose.yml build
docker compose -f docker/compose.yml up -d        # web ishga tushganda migratsiyalar o'zi bajariladi
docker compose -f docker/compose.yml exec web python manage.py check --deploy
```

Ishlayotgan ishlar worker qayta ishga tushganda `acks_late` tufayli navbatga qaytadi. Tadqiqotchi tugagan flow'larni qayta bajarmaydi (`progress.json`).

## 6. Claude API kaliti (TZ SEC-12)

- Kalit **faqat** `docker/worker.env` faylida turadi: `ANTHROPIC_API_KEY=sk-ant-...`. Fayl huquqi `600`, egasi — serverni boshqaradigan foydalanuvchi:

  ```bash
  sudo chown root:root docker/worker.env && sudo chmod 600 docker/worker.env
  ```

- Compose bu faylni faqat `worker` servisiga beradi. Web, beat va boshqa servislarda kalit yo'q. Buni `tests/test_deploy_files.py` tekshiradi.
- Kalit kodda, bazada, Dockerfile'da, loglarda va veb-interfeysda ko'rinmaydi. Log filtri `sk-ant-...` qiymatlarini va `x-api-key` sarlavhasini maskalaydi.
- Kalit bo'lmasa, worker ishga tushmaydi va sababini aniq yozadi: `docker compose logs worker`.

**Kalitni almashtirish:**

1. Anthropic Console'da yangi kalit yarating.
2. `docker/worker.env` ga yangi kalitni yozing.
3. Faqat worker'ni qayta ishga tushiring: `docker compose -f docker/compose.yml up -d --force-recreate worker`.
4. Ishlar yurayotganini tekshiring (`/ops/` yoki `docker compose logs worker`).
5. Shundan keyin eski kalitni Console'da o'chiring.

**Qo'shimcha himoya.** Anthropic Console'da tashkilot yoki workspace uchun oylik sarf limitini qo'ying. U server ichidagi limitlardan (FR-SV6: foydalanuvchi kunlik/oylik, server oylik) tashqari ikkinchi to'siq bo'ladi.

**Kalit chiqib ketsa:**

1. Darhol Console'da kalitni o'chiring (revoke).
2. Yangi kalit bilan yuqoridagi almashtirish tartibini bajaring.
3. Console'dagi sarf hisobotini va server `/ops/` dagi ishlar narxini solishtiring.
4. Kalit qayerdan chiqqanini aniqlang: `docker/worker.env` huquqlari, server foydalanuvchilari, zaxira nusxalar.

## 7. Monitoring

- `docker compose -f docker/compose.yml ps` — servislarning healthcheck holati.
- `docker compose -f docker/compose.yml logs -f worker web` — loglar. Ular secrets filtridan o'tadi.
- `/ops/` — ishlar, holatlar, narxlar, hodisalar.
- Diskni kuzating: MinIO volume'i, worker'ning `/app/var` papkasi (vaqtinchalik ish papkalari, ish tugagach o'chadi).
- Celery beat: `cleanup_expired` (har kuni 03:00) va `reap_stuck_jobs` (har 10 daqiqada).

## 8. E2E testlar (test profili)

`demo_shop` poligoni test profilida konteyner sifatida ishga tushadi. `yoriqnoma_server.settings.e2e` sozlamasi faqat `demo_shop` hostiga xususiy manzilga ruxsat beradi; production'da bunday ruxsat hech qachon yo'q.

```bash
cd server
docker compose -f docker/compose.yml -f docker/compose.test.yml --profile test up -d --build
uv run pytest -m server tests/e2e
```

Bu testlar haqiqiy Claude kalitini ishlatadi va pul sarflaydi.
