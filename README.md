# Blytz Capstone

Django app for Blytz Clothing design / orders. See [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) for product context and [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) for the full system architecture.

## Requirements

- Python 3.10+
- Windows / macOS / Linux

## Setup

```bash
# From the repository root
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux

python manage.py migrate
python manage.py seed_demo
python manage.py tailwind build
```

Edit `.env` as needed (`SECRET_KEY`, `ALLOWED_HOSTS`, `MESSENGER_PAGE_USERNAME`, etc.). For live AI design suggestions (Stage O), set `GEMINI_API_KEY` (see `.env.example`). Without a key, the editor AI panel uses the local demo fallback.

## Seed data

```bash
python manage.py seed_demo   # idempotent
```

| Email | Role | Notes |
| --- | --- | --- |
| `admin@blytz.demo` | Admin | Full access |
| `staff.accounting@blytz.demo` | Staff | Can edit accounting |
| `staff@blytz.demo` | Staff | Accounting view-only |
| `customer1@blytz.demo` … `customer5@blytz.demo` | Customer | Designs + orders |

Password for all demo users: `demo-pass-123`

## Roles

| Role | Access |
| --- | --- |
| **Customer** | `/app/` designs, editor, orders, profile |
| **Staff** | `/staff/` jobs, accounting (edit if granted), sales |
| **Admin** | Everything staff can, plus `/staff/payment-channels/`, `/staff/users/`, admin-only pages |

Role and permission changes apply on the user's next request.

## Run (development)

```bash
python manage.py tailwind runserver
# Or: python manage.py runserver
```

Open http://127.0.0.1:8000/

## Tests

```bash
python manage.py test
```

## Production (Railway)

- Set `DEBUG=False`, a strong `SECRET_KEY` (placeholder values are rejected when `DEBUG=False`), `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` (e.g. `https://your-app.up.railway.app`).
- Set `USE_SECURE_PROXY_SSL_HEADER=True` (or `SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https`).
- With `DEBUG=False`, secure cookies + `SECURE_SSL_REDIRECT` default on (override via `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` if needed).
- Optional MySQL: `DATABASE_URL=mysql://...` (PyMySQL is installed as MySQLdb).
- Start command via `Procfile`: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Static files: WhiteNoise. Run `python manage.py collectstatic` in the build.
- Media files are **not** auto-served by Django when `DEBUG=False` — configure object storage or a reverse-proxy later.
- Email: keep console locally; later set `EMAIL_BACKEND` to an anymail HTTPS provider and configure `ANYMAIL`.
- Capstone honesty: concurrency was verified on SQLite; no live payment provider; treat this as demo-ready, not “production proven.”

## Capstone demo walkthrough

1. Migrate + `seed_demo` + runserver (see Setup).
2. Customer `customer1@blytz.demo` / `demo-pass-123`: design → save → preview → submit with proof → Orders.
3. Staff `staff@blytz.demo` / `demo-pass-123`: Jobs → review order/mock-ups → payment accept/reject → advance phase.
4. Accounting: `/staff/accounting/` → **Export CSV** (staff/admin only).

## Routes

| Path | Who | Purpose |
| --- | --- | --- |
| `/` | Public | Landing |
| `/accounts/signup/` | Public | Sign up |
| `/accounts/login/` | Public | Log in |
| `/accounts/logout/` | Auth | Log out |
| `/accounts/confirm-email/`… | Public | Email verification |
| `/app/` | Customer | Dashboard |
| `/app/profile/` | Customer / staff | Profile |
| `/app/designs/` | Customer | Design list |
| `/app/designs/new/` | Customer | Create design (POST) |
| `/app/designs/<id>/` | Customer | Design detail |
| `/app/designs/<id>/editor/` | Customer | Editor + payment submit |
| `/app/designs/<id>/save/` | Customer | Save canvas (POST) |
| `/app/designs/<id>/submit/` | Customer | Submit + payment (POST) |
| `/app/designs/<id>/ai/suggest/` | Customer | Stage O AI two-candidate suggest (POST JSON) |
| `/app/orders/` | Customer | Order list |
| `/app/orders/<order_id>/` | Customer | Order detail |
| `/staff/` | Staff / admin | Staff overview |
| `/staff/jobs/` | Staff / admin | Jobs pipeline |
| `/staff/orders/<order_id>/` | Staff / admin | Staff order detail |
| `/staff/orders/<order_id>/advance/` | Staff / admin | Advance phase (POST) |
| `/staff/accounting/` | Staff / admin | Accounting list |
| `/staff/accounting/<order_id>/` | Staff / admin | Accounting detail |
| `/staff/sales/` | Staff / admin | Sales pipeline |
| `/staff/sales/<lead_id>/` | Staff / admin | Lead detail |
| `/staff/sales/<lead_id>/stage/` | Staff / admin | Update stage (POST) |
| `/staff/payment-channels/` | Admin | Payment channels |
| `/staff/payment-channels/add/` | Admin | Add channel |
| `/staff/payment-channels/<id>/edit/` | Admin | Edit channel |
| `/staff/payment-channels/<id>/deactivate/` | Admin | Deactivate (POST) |
| `/staff/users/` | Admin | User management |
| `/staff/users/add/` | Admin | Create staff |
| `/staff/users/<id>/` | Admin | Edit role / accounting / active |
| `/staff/admin-only/` | Admin | Admin smoke page |
| `/admin/` | Django admin | Built-in admin |
| `/dev/components/` | DEBUG | Component gallery |

## Layout

| Path | Purpose |
| --- | --- |
| `config/` | Settings, URLs, WSGI/ASGI |
| `apps/` | `accounts`, `core`, `designs`, `orders`, `accounting`, `sales` |
| `services/` | `proof_images`, `preview_images`, `ai_design` (Gemini); future email |
| BG removal | Client `@imgly/background-removal` (`static/js/remove_bg_client.js`) — no API key |
| `templates/` | Base layout and components |
| `static/` | CSS, JS, images |
| `media/` | Uploads (gitignored) |
| `src/styles/main.css` | Tailwind source + Blytz `@theme` tokens |
