# Развёртывание на Ubuntu 24.04 LTS

Полная инструкция: от чистого VPS до работающего сайта на HTTPS с Telegram-ботом.

Время: ~25 минут, если есть DNS и Telegram-токен.

---

## 0. Что нужно подготовить заранее

| Что | Где взять |
|---|---|
| **VPS с Ubuntu 24.04** | Любой — Hetzner, Selectel, Timeweb, Beget, DigitalOcean. Минимум: 1 vCPU, 1 ГБ RAM, 10 ГБ SSD. |
| **Доменное имя** | Если есть свой — настройте `A`-запись на IP сервера. Если нет — пропустите HTTPS-блок и используйте просто IP (Telegram WebApp без HTTPS работать не будет, но сайт и заявки — да). |
| **SSH-доступ** к VPS | По паролю или ключу. У большинства провайдеров — root по паролю при создании. |
| **Telegram bot token** | В Telegram → [@BotFather](https://t.me/BotFather) → `/newbot` → задать имя → получить токен вида `123456:ABC...`. **Если токен утёк — `/revoke`**, получите новый. |
| **Свой Telegram user ID** | [@userinfobot](https://t.me/userinfobot) → пришлёт цифру вроде `250323621`. |

---

## 1. Первичная настройка сервера

### 1.1. Зайти на сервер

```bash
ssh root@1.2.3.4
```

### 1.2. Обновить пакеты

```bash
apt update && apt upgrade -y
```

### 1.3. Создать пользователя `college` (не работайте под root)

```bash
adduser college               # задайте пароль
usermod -aG sudo college      # дать права sudo
mkdir -p /home/college/.ssh
cp ~/.ssh/authorized_keys /home/college/.ssh/ 2>/dev/null || true
chown -R college:college /home/college/.ssh
chmod 700 /home/college/.ssh
chmod 600 /home/college/.ssh/authorized_keys 2>/dev/null || true
```

Дальше всё — под `college`:

```bash
exit                          # выйти из root
ssh college@1.2.3.4
```

### 1.4. Файрвол

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # 80 + 443
sudo ufw enable               # ответьте y
sudo ufw status
```

---

## 2. Установка зависимостей

```bash
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx
python3 --version             # должно быть 3.12.x
```

---

## 3. Загрузка кода на сервер

Способ А — **через git** (рекомендую):

```bash
cd /home/college
git clone https://github.com/gegantarsgegant-cmyk/college-bot.git
cd college-bot
```

Способ Б — **через scp** (если репо приватный или вы хотите без git):

С локальной машины:

```bash
scp -r /путь/к/college-bot college@1.2.3.4:/home/college/
```

Способ В — **через rsync** (при обновлениях):

```bash
rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='data/' \
  /путь/к/college-bot/ college@1.2.3.4:/home/college/college-bot/
```

---

## 4. Виртуальное окружение и зависимости

```bash
cd /home/college/college-bot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Конфигурация (`.env`)

```bash
cp .env.example .env
nano .env
```

Заполните минимум эти поля:

```ini
PUBLIC_URL=https://college.example.com

# сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=<длинная_случайная_строка>

ADMIN_USERNAME=admin
ADMIN_PASSWORD=<свой_сложный_пароль>

TELEGRAM_BOT_TOKEN=<токен_от_BotFather>
TELEGRAM_ADMIN_IDS=250323621        # ваш ID, через запятую можно несколько

BOT_MODE=polling                    # оставить так — проще всего

DATABASE_URL=sqlite+aiosqlite:///./data/college.db
```

**Важно:** `chmod 600 .env`, чтобы никто кроме вас файл не прочитал:

```bash
chmod 600 .env
```

---

## 6. Шрифты и иконки (если есть свои)

Если у вас рядом с исходным `college.html` лежали папки `fonts/` и `favicon/` —

```bash
# скопируйте локально через scp:
# scp -r ./fonts college@1.2.3.4:/home/college/college-bot/app/static/
# scp -r ./favicon college@1.2.3.4:/home/college/college-bot/app/static/

ls app/static/fonts/        # должны быть .woff2 и fonts.css
ls app/static/favicon/      # favicon.ico, apple-touch-icon.png и т.д.
```

В этом репозитории шрифты и `fonts.css` уже включены в `app/static/fonts/` —
менять ничего не нужно.

---

## 7. Первый запуск (проверка)

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

В другом терминале:

```bash
curl -i http://127.0.0.1:8000/
```

Должен прийти HTTP `200`. Останавливаем (`Ctrl+C`) и идём дальше — настраивать systemd, чтобы сервис стартовал сам.

---

## 8. systemd-сервис (автозапуск)

Создайте файл сервиса:

```bash
sudo nano /etc/systemd/system/college-bot.service
```

Содержимое:

```ini
[Unit]
Description=Bible College website + Telegram bot
After=network.target

[Service]
Type=simple
User=college
Group=college
WorkingDirectory=/home/college/college-bot
EnvironmentFile=/home/college/college-bot/.env
ExecStart=/home/college/college-bot/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

# безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/college/college-bot/data /home/college/college-bot/app/static/uploads

[Install]
WantedBy=multi-user.target
```

Запустить и включить автозапуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now college-bot
sudo systemctl status college-bot         # должно быть "active (running)"
```

Логи:

```bash
journalctl -u college-bot -f              # в реальном времени
journalctl -u college-bot -n 200          # последние 200 строк
```

---

## 9. Nginx (reverse proxy)

```bash
sudo nano /etc/nginx/sites-available/college-bot
```

Замените `college.example.com` на ваш домен:

```nginx
server {
    listen 80;
    server_name college.example.com;

    # увеличиваем лимит для загрузки файлов в админке (фото преподов, документы)
    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 60s;
    }

    # отдаём статику напрямую через nginx — быстрее
    location /static/ {
        alias /home/college/college-bot/app/static/;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }
}
```

Активировать:

```bash
sudo ln -s /etc/nginx/sites-available/college-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Проверьте: откройте `http://college.example.com` — должен быть сайт.

---

## 10. HTTPS через Let's Encrypt (обязательно для Telegram WebApp)

DNS у домена должен уже указывать на сервер. Дальше:

```bash
sudo certbot --nginx -d college.example.com
```

Certbot задаст вопросы:
- **Email** — для уведомлений об истечении сертификата
- **Terms of Service** — `A`
- **Redirect HTTP → HTTPS** — выбирайте `2` (Redirect)

Готово. Сертификат продлевается сам через cron от certbot.

Проверьте:

```bash
curl -I https://college.example.com/
```

Должен прийти `200`. Откройте в браузере — должен быть замок 🔒.

---

## 11. Финальные шаги

### 11.1. Перезапуск сервиса

После любых изменений в `.env`:

```bash
sudo systemctl restart college-bot
```

### 11.2. Первый вход в админку

Откройте: `https://college.example.com/admin/login`

- Логин: `admin`
- Пароль: тот, что вы задали в `.env` (`ADMIN_PASSWORD`)

После входа сразу смените пароль в дашборде.

### 11.3. Проверка Telegram-бота

В Telegram найдите своего бота → `/start`. Должно прилететь приветствие со статистикой и кнопкой «🛠 Открыть админ-панель» (Mini App работает только когда сайт на HTTPS).

Отправьте тестовую заявку через сайт → бот должен прислать карточку заявки с кнопками «⏳ В работу / ✅ Принять / ✖ Отклонить» и WebApp-кнопкой.

---

## 12. Резервное копирование

База лежит в одном файле. Простой ежедневный бэкап через cron:

```bash
sudo crontab -e -u college
```

Добавьте:

```cron
0 3 * * * cd /home/college/college-bot && cp data/college.db /home/college/backups/college-$(date +\%Y\%m\%d).db && find /home/college/backups -name 'college-*.db' -mtime +30 -delete
```

```bash
mkdir -p /home/college/backups
```

Скачать бэкап локально:

```bash
scp college@1.2.3.4:/home/college/backups/college-20260101.db ./
```

Также бэкапьте `app/static/uploads/` — там фото преподавателей и документы.

---

## 13. Обновление до новой версии

```bash
cd /home/college/college-bot
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart college-bot
```

База мигрирует автоматически (SQLAlchemy `create_all` создаёт новые поля; для несовместимых изменений будут отдельные миграции в релизных заметках).

---

## 14. Альтернатива: Docker

Если предпочитаете контейнеры:

```bash
sudo apt install -y docker.io docker-compose-plugin
cd /home/college/college-bot
cp .env.example .env && nano .env
sudo docker compose up -d --build
sudo docker compose logs -f
```

Nginx + Let's Encrypt настройте по тому же шагу 9–10, проксируйте на `127.0.0.1:8000`.

---

## 15. Траблшутинг

| Симптом | Что проверить |
|---|---|
| `502 Bad Gateway` | `sudo systemctl status college-bot` — сервис упал. `journalctl -u college-bot -n 100` — увидеть стек. |
| Бот не отвечает | `journalctl -u college-bot \| grep -i bot` — токен правильный? `TELEGRAM_BOT_TOKEN=` не пустой? |
| Заявка не приходит в Telegram | `TELEGRAM_ADMIN_IDS` — ваш numeric ID? Бот не заблокирован вами в личке? Хоть раз отправьте боту `/start`. |
| Кнопка WebApp не открывается | Сайт должен быть на HTTPS. Telegram блокирует WebApp без HTTPS. |
| Шрифты не грузятся | `ls /home/college/college-bot/app/static/fonts/` — файлы на месте? `curl -I https://college.example.com/static/fonts/fonts.css` → 200? |
| Загрузка фото преподавателя падает | `client_max_body_size 25M;` есть в Nginx? Папка `app/static/uploads/` writable пользователем `college`? |
| Сменили пароль и забыли | `sqlite3 data/college.db "DELETE FROM admin_users;"` → перезапустить сервис → создастся новый из `.env`. |

---

## 16. Чеклист безопасности

- [ ] `chmod 600 .env`
- [ ] `ADMIN_PASSWORD` ≠ `admin123`, минимум 12 символов
- [ ] `SECRET_KEY` сгенерирован случайно (не из примера)
- [ ] `ufw enable` и открыты только `22, 80, 443`
- [ ] SSH по ключу, не по паролю (`PasswordAuthentication no` в `/etc/ssh/sshd_config`)
- [ ] Регулярный `apt upgrade -y` (можно автомат: `sudo apt install unattended-upgrades`)
- [ ] HTTPS включён (Telegram WebApp требует)
- [ ] Резервное копирование настроено (см. §12)
