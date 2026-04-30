# Bible College ХВЕ — site + Telegram bot + admin

A self-contained website + Telegram bot + mini admin panel for the
**Библейский Колледж ХВЕ** (Minsk). One Python process serves:

- the public website (`/`) — your existing `college.html` design, but with all
  data (teachers, contact info, application form, etc.) coming from a database;
- a JSON API for the application form (`/api/applications`);
- a web admin panel at **`/admin`** (login required) for managing news,
  events, teachers, gallery, documents, settings and applications;
- a Telegram bot (aiogram) that mirrors the same admin features inside Telegram
  and lets visitors browse content, get notified of news, and submit
  applications via a guided FSM.

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

Public:

- `/start` — greeting + reply keyboard menu
- `/news` — latest 5 news items
- `/events` — upcoming events
- `/programs` — programmes summary
- `/teachers` — teachers list
- `/documents` — published documents
- `/contacts` — contacts
- `/apply` — start the guided application flow

Admin (only for users in `TELEGRAM_ADMIN_IDS`):

- `/admin` — open inline admin menu
- `/applications` — list new applications
- `/newpost` — create a news item
- `/newevent` — create an event
- `/newteacher` — add a teacher
- `/newdoc` — upload a document
- `/cancel` — abort an in-progress wizard

When a new application arrives (web or bot), every admin gets a Telegram
message with three inline buttons: **в работу / принято / отклонить**.

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
