# Ревизор — развёртывание на своём сервере

Инструкция рассчитана на чистый Ubuntu 22.04/24.04 с root-доступом.
Домен и IP подставь свои.

## Что понадобится

- сервер (1 CPU / 1 ГБ RAM хватит: пайплайн лёгкий, LLM не используется);
- домен, A-запись которого смотрит на IP сервера;
- доступ по SSH.

## Вариант 1: Docker (рекомендую)

```bash
# на сервере
apt update && apt install -y git docker.io docker-compose-v2
git clone https://github.com/MKristof2008/Xakton-ot-HSE.git app
cd app

# ключи модели — только через .env, в git он не попадает
cp ml/.env.example ml/.env
nano ml/.env          # вписать LLM_API_KEY

docker compose up -d --build
docker compose logs -f          # смотреть, как поднимается
curl -s localhost:8000/api/health
```

Сервис слушает только `127.0.0.1:8000`, наружу его отдаёт nginx.

## Вариант 2: без Docker

```bash
apt update && apt install -y python3.12 python3.12-venv nginx git
git clone https://github.com/MKristof2008/Xakton-ot-HSE.git app
cd app

python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# ключи модели
cp ml/.env.example ml/.env
nano ml/.env          # вписать LLM_API_KEY

# собрать фронт (нужен node 20+)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
cd frontend && npm ci && npm run build && cd ..

# сервис
cat > /etc/systemd/system/provereno.service <<'EOF'
[Unit]
Description=Provereno factcheck
After=network.target

[Service]
WorkingDirectory=/root/app
Environment=VERDICT_DB=/root/app/data/verdict.db
ExecStart=/root/app/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now provereno
systemctl status provereno
```

## nginx и HTTPS

```bash
cat > /etc/nginx/sites-available/provereno <<'EOF'
server {
    listen 80;
    server_name ваш-домен.ru www.ваш-домен.ru;

    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
EOF

ln -s /etc/nginx/sites-available/provereno /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# бесплатный сертификат
apt install -y certbot python3-certbot-nginx
certbot --nginx -d ваш-домен.ru -d www.ваш-домен.ru
```

## Проверка после деплоя

```bash
curl -s https://ваш-домен.ru/api/health
# {"status":"ok","llm":false,...}

curl -s -X POST https://ваш-домен.ru/api/check \
  -H 'Content-Type: application/json' \
  -d '{"text":"ЦБ поднял ключевую ставку до 21% годовых 25 октября 2024 года."}'
# {"verdict":"правда","score":90,...}
```

Открой домен в браузере — должен открыться интерфейс.

## Обновление

```bash
cd app && git pull && docker compose up -d --build
# или без Docker: systemctl restart provereno
```

## Что важно знать

- **База живёт в томе** `provereno_data` (Docker) или `data/verdict.db`.
  При пересборке контейнера данные сохраняются.
- **Банк знаний** (`ml/lakmus/data/knowledge_bank.json`) пополняется при
  проверках. В git едет только шаблон `.example`; рабочий файл создаётся
  сам. Чтобы не потерять его при пересборке, вынесите на том:
  `VERDICT_BANK=/data/knowledge_bank.json` в `environment`.
- **Один воркер.** Хранилище — SQLite, топы считаются по нему же. Если понадобится
  несколько воркеров, выносить состояние в Postgres и считать топы отдельно.
- **Резервная копия:** `docker compose exec provereno cp /data/verdict.db /data/backup.db`
  и забрать файл, либо `sqlite3 data/verdict.db .dump`.
- **Ключи только в `.env`.** `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`.
  Уровни тарифов можно развести: `LLM_MODEL_BASE`, `LLM_MODEL_PLUS`,
  `LLM_MODEL_MAX`. Файл `.env` в git не попадает.
- **Аккаунты для жюри** создаются скриптом:
  `python -I ml/tools/prepare_demo.py --all --apply`. Он же чистит
  демо-следы и печатает логины с паролем.

## Аккаунты для жюри

| Логин | Пароль | Тариф |
|---|---|---|
| `jury-base@revizor.demo` | `revizor-2026` | База |
| `jury-plus@revizor.demo` | `revizor-2026` | Плюс |
| `jury-max@revizor.demo` | `revizor-2026` | Макс |
| `jury-max-2@revizor.demo` | `revizor-2026` | Макс |

Инструкция для жюри — [`JURY_GUIDE.md`](JURY_GUIDE.md).
