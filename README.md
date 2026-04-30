# Bible College ХВЕ — site + Telegram bot + admin

A self-contained website + admin-only Telegram bot for the
**Библейский Колледж ХВЕ** (Minsk). One Python process serves:

- **Public website (`/`)** — your existing `college.html` design, but with all
  data (teachers, contact info, programmes, application form, …) backed by a
  database. Visitors only ever interact with the site.
- **Application API (`/api/applications`)** — the website form posts here; new
  applications are stored in DB and pushed into Telegram.
- **Web admin panel (`/admin`)** — login-protected, full CRUD for news, events,
  teachers, gallery, documents, applications and site settings (titles,
  contacts, social links, statistics).
- **Telegram Mini App (`/admin/tg`)** — same admin panel auto-authenticated via
  Telegram WebApp `initData` HMAC; opens directly inside Telegram from the bot's
  inline buttons. Designed for managing the site on the go.
- **Admin-only Telegram bot** — receives new-application notifications with
  inline action buttons (✓ В работу / ✓ Принято / ✗ Отклонить + 🛠 Открыть
  админку). Provides quick FSM commands for creating news, events, teachers and
  documents from the chat. **Non-admin users get a polite redirect to the
  website**; the bot is not meant for the public.

## Quick start (Docker)

```bash
git clone <this-repo>
cd college-bot
cp .env.example .env
# edit .env and set at minimum:
#   SECRET_KEY=...
#   ADMIN_USERNAME=admin
#   ADMIN_PASSWORD=<something secure>
#   TELEGRAM_BOT_TOKEN=<from @BotFather>
#   TELEGRAM_ADMIN_IDS=<your-numeric-id>   # get from @userinfobot
#   PUBLIC_URL=https://your-domain.tld     # https required for Mini App

# Drop your existing assets next to the app:
mkdir -p app/static/fonts app/static/favicon
cp -r /path/to/your/fonts/*   app/static/fonts/
cp -r /path/to/your/favicon/* app/static/favicon/

docker compose up -d --build
```

Visit:

- `http://<host>:8000/` — public site
- `http://<host>:8000/admin/` — admin panel (use `ADMIN_USERNAME`/`ADMIN_PASSWORD`)

## Quick start (without Docker)

Requires Python 3.11+:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit values
python -m app
```

## Environment variables

See `.env.example` for the full list. The most important ones:

| Variable | Description |
|---|---|
| `PUBLIC_URL` | Public URL of the site. **Must be HTTPS** for the Telegram Mini App button to work. |
| `SECRET_KEY` | Random string for signing admin cookies. |
| `ADMIN_USERNAME`/`ADMIN_PASSWORD` | Initial admin credentials, created on first start. |
| `TELEGRAM_BOT_TOKEN` | From @BotFather. If empty, the bot is disabled. |
| `TELEGRAM_ADMIN_IDS` | Comma-separated numeric Telegram user IDs allowed to use admin commands and receive new-application notifications. |
| `TELEGRAM_NOTIFY_CHAT_ID` | Optional channel/group ID where new applications are forwarded. |
| `BOT_MODE` | `polling` (default; works on any VPS) or `webhook` (requires public HTTPS). |
| `DATABASE_URL` | Default: SQLite at `./data/college.db`. Use `postgresql+asyncpg://…` for production scale. |

## Deploying behind HTTPS

Telegram Mini Apps require HTTPS. Easiest path on a Linux VPS:

```bash
sudo apt install nginx certbot python3-certbot-nginx
# Point your domain at the server, then:
sudo certbot --nginx -d college.example.com
```

Sample `nginx` server block:

```nginx
server {
    listen 443 ssl;
    server_name college.example.com;
    ssl_certificate     /etc/letsencrypt/live/college.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/college.example.com/privkey.pem;

    client_max_body_size 20m;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

## Bot commands

The bot is **admin-only**. Users not listed in `TELEGRAM_ADMIN_IDS` get a
short message pointing them to the public website and nothing else.

Admin commands (only for users in `TELEGRAM_ADMIN_IDS`):

- `/start`, `/admin` — open inline admin menu (with the WebApp button to the
  full admin panel and quick action buttons)
- `/applications` — list new applications
- `/newpost` — create a news item
- `/newevent` — create an event
- `/newteacher` — add a teacher
- `/newdoc` — upload a document
- `/cancel` — abort an in-progress wizard
- `/help` — show this list

When a new application arrives from the website, every admin in
`TELEGRAM_ADMIN_IDS` (and optionally `TELEGRAM_NOTIFY_CHAT_ID`) gets a Telegram
message with inline buttons: **✓ В работу / ✓ Принято / ✗ Отклонить** and (if
`PUBLIC_URL` is HTTPS) **🛠 Открыть в админке** which opens the relevant
application inside the Telegram Mini App.

## Telegram Mini App / WebApp setup

For the *Mini App* button (`web_app=…`) to work, Telegram requires a public
HTTPS URL. After you have HTTPS:

1. Open [@BotFather](https://t.me/BotFather) → `/mybots` → pick your bot.
2. *Bot Settings → Configure Mini App* → **Edit Mini App URL** → paste
   `https://your-domain.tld/admin/tg`.
3. (Optional) *Bot Settings → Menu Button* → set the menu button to the same
   URL so admins can also open the panel from the Telegram chat header.

The page at `/admin/tg` reads `Telegram.WebApp.initData`, posts it to
`/admin/tg/auth`, the server verifies the HMAC against `TELEGRAM_BOT_TOKEN`,
checks that the Telegram user is in `TELEGRAM_ADMIN_IDS` and issues an admin
session cookie. No password is needed inside Telegram.

If `PUBLIC_URL` is not HTTPS the bot falls back gracefully: the WebApp button
is hidden and admins can still log into `/admin/login` with the username /
password from `.env`.

## Project layout

```
college-bot/
├── app/
│   ├── __main__.py
│   ├── main.py            FastAPI app + lifespan
│   ├── config.py
│   ├── db.py
│   ├── models.py          SQLAlchemy models
│   ├── services.py        shared logic (DB queries)
│   ├── auth.py            cookie-signed admin sessions
│   ├── security.py        bcrypt
│   ├── uploads.py         safe file uploads
│   ├── routers/
│   │   ├── site.py        public site
│   │   ├── api.py         /api/applications, /api/teachers
│   │   └── admin.py       /admin/* CRUD
│   ├── bot/
│   │   ├── bot.py         aiogram lifecycle
│   │   ├── handlers.py    public + admin handlers
│   │   ├── states.py      FSM states
│   │   └── notifier.py    cross-module notifier
│   ├── templates/
│   │   ├── index.html     full college site (Jinja2)
│   │   └── admin/         admin panel templates
│   └── static/
│       ├── fonts/         drop your fonts.css + font files here
│       ├── favicon/       drop favicon.ico here
│       └── uploads/       runtime uploads (images, PDFs)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## Migrating to Postgres

```
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/college
```

(SQLAlchemy will create tables automatically on first start.)

## Backups

- Database: `data/college.db` (with SQLite). Just copy the file.
- Uploads: `app/static/uploads/`.

A simple cron job is enough:
```
0 3 * * * tar czf /backup/college-$(date +\%F).tgz /srv/data /srv/app/static/uploads
```
