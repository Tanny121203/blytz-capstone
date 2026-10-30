# Blytz — Project Brief

Blytz is a Django web app for a custom apparel / design business. Staff manage designs, orders, sales, and accounting; customers discover designs and can be routed to Facebook Messenger for checkout support. AI helpers and transactional email live behind thin wrappers in `services/`; background removal runs client-side (`@imgly/background-removal`).

## Product goals

- Design catalog and upload pipeline (optional client BG removal / AI cleanup)
- Order lifecycle with a short payment confirmation window
- Sales and accounting views for day-to-day operations
- Staff accounts with role-aware access (custom User in Prompt 2)
- Messenger deep-link using `MESSENGER_PAGE_USERNAME`

## Tech stack

| Layer | Choice |
| --- | --- |
| Framework | Django 5.x |
| Settings | django-environ |
| Database | SQLite by default; `DATABASE_URL` for MySQL later |
| CSS | Tailwind CSS via django-tailwind-cli (no Node) |
| Static | WhiteNoise |
| Email (dev) | Console backend |

## Layout

```
manage.py
config/          # project settings, urls, wsgi/asgi
apps/            # accounts, core, designs, orders, accounting, sales
services/        # AI / email wrappers (email later); BG removal is client-side
templates/       # base + components
static/          # css, js, img
media/           # user uploads (gitignored)
docs/            # this brief and future docs
```

## Business settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `MESSENGER_PAGE_USERNAME` | *(from env)* | Facebook Messenger page username for customer deep-links |
| `PAYMENT_WINDOW_MINUTES` | `10` | Minutes allowed to confirm payment after order creation |
| `PROOF_MAX_UPLOAD_MB` | `15` | Max payment-proof upload size (client + server) |

## Brand / Tailwind theme

Default UI is black and white. Gold is optional — border or soft background accent only, never the primary fill for actions. Mobile-first; keep focus rings visible.

| Token | Hex | Role |
| --- | --- | --- |
| `ink` | `#0A0A0A` | Text, primary buttons, strong borders |
| `ink-muted` | `#525252` | Secondary text |
| `ink-subtle` | `#737373` | Hints / placeholders |
| `canvas` | `#FFFFFF` | Page background |
| `surface` | `#FAFAFA` | Soft panels |
| `border` | `#E5E5E5` | Default borders |
| `border-strong` | `#0A0A0A` | Emphasized borders |
| `gold` | `#C9A227` | Optional accent (border / soft bg) |
| `gold-soft` | `#F7F1DE` | Optional soft gold surface |
| `danger` / `success` / `warning` | — | Status only |

Typography:

- Headings: **Playfair Display** (`font-display`)
- Body: GitHub-style system stack (`font-sans`)

## Development notes

1. Run `migrate` after pulling; `AUTH_USER_MODEL` is `accounts.User`.
2. Default DB is SQLite; set `DATABASE_URL` when switching to MySQL.
3. Prefer `python manage.py tailwind runserver` so the Tailwind watcher runs with Django.
4. Keep third-party API clients in `services/`; apps call those wrappers, not SDKs directly.
5. Auth: django-allauth with mandatory email verification; console email in development.

## 4. Data models

| Model | App | Notes |
| --- | --- | --- |
| `User` | accounts | Email login; `role`; `phone`; `can_edit_accounting`; helper `can_edit_accounting_page()` |
| `PaymentChannel` | orders | `kind` (gcash/maya/bank), account fields, QR, `is_active` |
| `Design` | designs | Owner, garment fields, `canvas_json`, preview; unsubmitted = no related order |
| `Order` | orders | `order_id` `BLY-000001`; statuses job_request → completed; front/back preview PNGs at submit; `final_design` (+ version / approval timestamps); `agreed_total`; derived totals count **accepted** payments only; `has_accepted_payment` / `pending_payment` |
| `OrderPhaseChange` | orders | Phase audit: from/to status, changed_by, changed_at |
| `Payment` | orders | P2P claim: `amount_claimed` + `proof_file`; `status` pending/accepted/rejected; staff review fields; many per order (one pending max) |
| `Lead` | sales | Created on submission; stages new_lead → completed / lost |
| `ActivityLog` | designs | design_created / submitted / revised / approved, order_confirmed |

Seed: `python manage.py seed_demo` (idempotent). Demo password: `demo-pass-123`.
