# Blytz — System Architecture

**Product:** Blytz Clothing — custom apparel design and order operations  
**Framework:** Django 5.x  
**Document purpose:** Complete current-state system architecture for download, sharing, and onboarding.  
**Related:** [PROJECT_BRIEF.md](PROJECT_BRIEF.md) (product goals & brand), [README.md](../README.md) (setup & routes)

---

## Table of contents

1. [Executive overview](#1-executive-overview)
2. [Tech stack](#2-tech-stack)
3. [Repository layout](#3-repository-layout)
4. [High-level architecture](#4-high-level-architecture)
5. [Application domains](#5-application-domains)
6. [Data model](#6-data-model)
7. [Authentication & authorization](#7-authentication--authorization)
8. [URL map & request routing](#8-url-map--request-routing)
9. [Core business workflows](#9-core-business-workflows)
10. [Frontend & UI architecture](#10-frontend--ui-architecture)
11. [Design editor contract](#11-design-editor-contract)
12. [Services layer](#12-services-layer)
13. [Configuration & environment](#13-configuration--environment)
14. [Static assets, media & Tailwind](#14-static-assets-media--tailwind)
15. [Deployment](#15-deployment)
16. [Seed data & demo accounts](#16-seed-data--demo-accounts)
17. [Testing](#17-testing)
18. [Error handling & security notes](#18-error-handling--security-notes)
19. [Planned / not-yet-implemented](#19-planned--not-yet-implemented)
20. [Quick reference matrices](#20-quick-reference-matrices)

---

## 1. Executive overview

Blytz is a server-rendered Django web application for a custom apparel business. Customers create garment designs in a browser editor, submit them with a peer-to-peer (P2P) payment claim (proof upload), and track order progress. Staff manage a jobs pipeline, sales leads, and accounting. Admins manage users and payment channels.

**Architectural style**

| Aspect | Choice |
| --- | --- |
| Presentation | Django templates + Tailwind CSS (no SPA framework) |
| API style | Mostly form POSTs; JSON responses for AJAX editor save/submit |
| Auth | django-allauth (email login, mandatory verification) |
| Persistence | SQLite by default; MySQL via `DATABASE_URL` |
| Domain split | Django apps under `apps/<name>`; project package `config/` |
| Third-party I/O | Intended behind `services/` wrappers (stubs today) |
| Money model | P2P **claims** — customers upload proof; staff accept/reject; only **accepted** payments count as paid; no payment gateway |

**Primary actors**

- **Customer** — source of submissions: designs, editor, payment claims, order history (`/app/`)
- **Staff** — sink for review and ops: jobs pipeline, order/design inspection, phase advances, payment accept/reject, sales, accounting (view; edit if granted) (`/staff/`)
- **Admin** — everything staff can, plus users, payment channels, admin-only pages

There is no separate Front Desk actor. Job/order phase (`Order.status`) is distinct from derived payment status (`Order.payment_status`: Fully Paid / Outstanding Balance).

---

## 2. Tech stack

| Layer | Technology | Notes |
| --- | --- | --- |
| Language | Python 3.10+ | |
| Web framework | Django 5.2.x | `manage.py` at repo root; settings in `config/` |
| WSGI server | Gunicorn | Production (`Procfile`) |
| Settings / env | django-environ | `.env` + `.env.example` |
| Auth | django-allauth | Email-only login; mandatory email verification |
| CSS | Tailwind via django-tailwind-cli | No Node toolchain |
| Static serving | WhiteNoise | Compressed manifest storage when `DEBUG=False` |
| Images | Pillow | Seed QR placeholders; design/order previews; payment-proof shrink/sanitize |
| MySQL driver | PyMySQL | Installed as MySQLdb in `config/__init__.py` |
| Email (dev) | Django console backend | Anymail optional later |
| Hosting target | Railway | TLS proxy header support |

**Pinned / key dependencies** (`requirements.txt`): Django, django-allauth, django-environ, django-tailwind-cli, gunicorn, Pillow, PyMySQL, whitenoise.

---

## 3. Repository layout

```
manage.py                 # Django entrypoint (must stay at repo root)
config/                   # Project package
  settings.py             # Environ, apps, auth, static/media, business settings
  urls.py                 # Root URLConf + DEBUG media serving
  wsgi.py / asgi.py
  __init__.py             # PyMySQL → MySQLdb shim
apps/
  accounts/               # Custom User, roles, profile, staff home, user admin
  core/                   # Landing, component gallery, context processors
  designs/                # Design CRUD/editor, ActivityLog, submit transaction
  orders/                 # Order, Payment, PaymentChannel, jobs pipeline
  accounting/             # Staff accounting views (no own models)
  sales/                  # Lead pipeline
services/                 # proof_images, preview_images, ai_design (+ email later)
templates/                # Root templates + components + per-app pages
static/                   # css/, js/, img/, garments/ (SVG mockups + garments.json)
src/styles/main.css       # Tailwind source + @theme tokens
media/                    # Uploads (gitignored): payment_channels, payment_proofs, …
docs/                     # PROJECT_BRIEF.md, this file
Procfile                  # gunicorn bind
.env.example              # Documented env vars
```

**Conventions (workspace rules)**

- Domain code in `apps/<name>` with `name = "apps.<name>"` in each `apps.py`
- Register apps as `"apps.<name>"` in `INSTALLED_APPS`
- Apps call `services/` wrappers — not third-party SDKs directly
- Templates in root `templates/`; static in root `static/`; uploads in `media/`

---

## 4. High-level architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Browser (customer / staff)                       │
│  Templates (base_public / base_customer / base_staff) + Tailwind CSS     │
│  JS: editor_*.js, editor_chrome.js, payment_*.js, nav.js, ui.js          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS
┌───────────────────────────────▼─────────────────────────────────────────┐
│                     Reverse proxy (e.g. Railway)                         │
│                     → Gunicorn → config.wsgi                             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                         Django middleware stack                          │
│  Security → WhiteNoise → Session → Common → CSRF → Auth → Messages →    │
│  XFrame → allauth AccountMiddleware                                     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│  URLConf (config.urls)                                                   │
│  allauth · designs · orders · accounting · sales · accounts · core       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Role guards   │     │ Domain views    │     │ Django admin    │
│ decorators /  │     │ forms, models   │     │ /admin/         │
│ mixins        │     │ transactions    │     │                 │
└───────┬───────┘     └────────┬────────┘     └────────┬────────┘
        │                      │                       │
        └──────────────────────┼───────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Database (SQLite default · MySQL via DATABASE_URL)                      │
│  User · Design · ActivityLog · Order · OrderPhaseChange · Payment ·     │
│  PaymentChannel · Lead                                                   │
└─────────────────────────────────────────────────────────────────────────┘

services/:
  proof_images · preview_images · ai_design (live)  ·  email (planned)
  # BG removal: client-side @imgly (static/js/remove_bg_client.js)
```

**Request path principles**

1. Public marketing and auth pages use `base_public.html` / allauth templates.
2. Customer area is gated by `@customer_required` → `base_customer.html`.
3. Staff/admin area is gated by `@staff_required` / `@admin_required` → `base_staff.html`.
4. Cross-cutting template context comes from `apps.core.context_processors.blytz` (Messenger URL, payment window, DEBUG).

---

## 5. Application domains

### 5.1 `apps.accounts`

| Responsibility | Details |
| --- | --- |
| Custom user | Email as `USERNAME_FIELD`; roles `customer` / `staff` / `admin`; `phone`; `can_edit_accounting` |
| Auth adapter | Post-login: staff/admin → `/staff/`; customers → `/app/` |
| Signup | `BlytzSignupForm` — optional phone; forces `role=customer` |
| Profile | Customers and staff can edit name/phone/email |
| Staff home | Dashboard stats + Chart.js overview (orders by phase, new orders/30d, pending-payment tile) |
| User management | Admin-only: list, create staff, edit role / accounting flag / active |
| Guards | `decorators.py` (FBV) and `mixins.py` (CBV): customer / staff / admin |

**User helpers**

- `is_customer`, `is_staff_role` (staff **or** admin), `is_admin_role`
- `can_edit_accounting_page()` — admins always; staff only if `can_edit_accounting`

**User management safety rules**

- Cannot demote or deactivate yourself
- System must keep at least one active admin
- Creating staff sets `is_staff=True`; editing syncs `is_staff` / `is_superuser` from role

### 5.2 `apps.core`

| Responsibility | Details |
| --- | --- |
| Landing | Public home with how-it-works, gallery placeholders, testimonials, FAQs. Authenticated visitors are redirected: customers → `/app/`, staff/admin → `/staff/` |
| Context processor | `MESSENGER_PAGE_USERNAME`, `messenger_url` (`https://m.me/...`), `PAYMENT_WINDOW_MINUTES`, `DEBUG` |
| Component gallery | `/dev/components/` (+ customer/staff variants) — **DEBUG only** |
| Models | None (placeholder files) |

### 5.3 `apps.designs`

| Responsibility | Details |
| --- | --- |
| Design ownership | Customer-owned drafts; submitted = has related `Order` |
| Editor | Canvas JSON save; inline draft title rename (saved with Save); submit with payment claim. Saves (including rename) rejected once a related Order exists |
| ActivityLog | Audit trail across design/order/lead lifecycle |
| Forms | `DesignSaveForm`, `DesignSubmitForm` (proof + front/back preview PNGs, window timestamp) |

### 5.4 `apps.orders`

| Responsibility | Details |
| --- | --- |
| Orders | `BLY-######` IDs; phase pipeline; agreed totals; payment aggregates (accepted only); final design upload/approval |
| Payments | Customer claims (pending → staff review); staff/admin manual adjustments (auto-accepted) |
| PaymentChannel | GCash / Maya / Bank; QR; active flag — admin CRUD |
| Jobs UI | Kanban-style pipeline + staff order detail (mock-ups, final design in Pending Edit, design details, phase history, artwork download) + advance phase + payment review |

### 5.5 `apps.accounting`

| Responsibility | Details |
| --- | --- |
| Views only | No domain models — operates on `Order` / `Payment` |
| List | Totals collected / outstanding; Chart.js (collected vs outstanding, collections/30d, by channel — **accepted only**); pending-payment marker; edit capability flag |
| Detail | Payment status per row; set `agreed_total`; add manual payment adjustments (auto-accepted) |

### 5.6 `apps.sales`

| Responsibility | Details |
| --- | --- |
| Lead | One-to-one with `Order`; stage pipeline |
| Pipeline UI | Stages columns + “incomplete designs” tab |
| Lead detail | Customer activity timeline from `ActivityLog` |

### 5.7 `services/`

| Module | Role |
| --- | --- |
| `proof_images.py` | Verify/shrink PNG/JPEG proofs (EXIF orientation, strip metadata incl. GPS, max edge 2000 px, PNG optimize / JPEG ~q85); PDFs unchanged |
| `preview_images.py` | Validate submit mock-up PNGs (real PNG via Pillow, ≤5 MB, max edge 2400 px) |
| `ai_design.py` | Stage O Gemini two-candidate suggestions |
| *(planned)* | transactional email |

Background removal is **client-side** (`@imgly/background-removal` via `static/js/remove_bg_client.js`), not a `services/` wrapper.

Apps call wrappers here rather than vendor SDKs directly.

---

## 6. Data model

### 6.1 Entity-relationship overview

```
User (accounts)
 ├──< Design (designs) ──< Order (orders) >── PaymentChannel
 │         │                    │                  ▲
 │         │                    ├──< Payment ──────┘
 │         │                    ├──< OrderPhaseChange
 │         │                    └─── Lead (sales) 1:1
 │         └── ActivityLog ─────────┘
 └── can_edit_accounting (staff flag)
```

### 6.2 `accounts.User`

| Field | Type | Notes |
| --- | --- | --- |
| email | EmailField, unique | Login identifier |
| phone | CharField | Optional |
| role | TextChoices | `customer` \| `staff` \| `admin` (default customer) |
| first_name / last_name | CharField | |
| can_edit_accounting | Boolean | Staff-only meaning; admins bypass via helper |
| is_staff / is_active / is_superuser | Django flags | Synced with role on admin user edit |
| date_joined | DateTime | |

`UserManager.create_superuser` requires `role=admin`, `is_staff`, `is_superuser`.

### 6.3 `designs.Design`

| Field | Type | Notes |
| --- | --- | --- |
| owner | FK → User | CASCADE |
| title | CharField | Default “Untitled design” on create |
| garment_template | CharField | Allow-list: `tee`, `polo`, `hoodie`, `jersey` (aliases normalized by migration / editor load) |
| garment_color | CharField | e.g. `black` |
| canvas_json | JSONField | Editor state (`version`, `objects`, …) |
| preview_image | ImageField | `design_previews/` (optional) |
| created_at / updated_at | DateTime | |

**Derived:** `is_submitted` — true if any related `Order` exists (uses prefetch cache when available).

### 6.4 `designs.ActivityLog`

| Kind | When |
| --- | --- |
| `design_created` | New draft |
| `design_submitted` | Submit creates order |
| `design_revised` | Staff replaces final design (version > 1) |
| `design_approved` | Customer approves final design → Production |
| `order_confirmed` | Logged on submit (and seed) |
| `phase_moved` | Staff advances order phase |
| `lead_stage_changed` | Staff changes lead stage |

Links: `customer` (required), optional `design`, optional `order`.

### 6.5 `orders.PaymentChannel`

| Field | Type | Notes |
| --- | --- | --- |
| kind | TextChoices | `gcash` \| `maya` \| `bank` |
| display_name | CharField | |
| account_name / account_number | CharField | |
| qr_image | ImageField | `payment_channels/` |
| instructions | TextField | |
| is_active | Boolean | Inactive channels hidden from customer submit |

### 6.6 `orders.Order`

| Field | Type | Notes |
| --- | --- | --- |
| order_id | CharField unique | Auto `BLY-000001` via `select_for_update` max |
| customer | FK → User | PROTECT |
| design | FK → Design | PROTECT |
| canvas_json_snapshot | JSONField | Frozen at submit |
| preview_image | ImageField | `order_previews/` — front mock-up (garment + artwork) required at submit |
| preview_back_image | ImageField | `order_previews/` — back mock-up required at submit |
| final_design | FileField | `final_designs/` — staff print-ready file (png/jpg/jpeg/pdf); not shrunk |
| final_design_version | PositiveInteger | Starts at 0; increments on each upload/replace (no history kept) |
| final_design_uploaded_at | DateTime nullable | Set on each final-design upload |
| approved_version | PositiveInteger nullable | Version the customer approved |
| approved_at | DateTime nullable | When the customer approved |
| status | TextChoices | See phase flow |
| agreed_total | Decimal nullable | Set by accounting |
| notes | TextField | |
| accounting_edited_by / accounting_edited_at | Audit | Last accounting edit |
| created_at | DateTime | |

**Final design helpers:** `final_design_is_pdf` / `final_design_is_image`; `can_approve_final_design()` — true only in `pending_edit` with a file and version ≥ 1.

**Phase flow (strict forward-only):**

```
job_request → pending_edit → production → completed
```

**Derived payment properties** (accepted payments only)

| Property | Logic |
| --- | --- |
| `total_paid` | Sum of `payments.amount_claimed` where `status=accepted` |
| `balance` | `agreed_total - total_paid` (None if no agreed total) |
| `payment_status` | `"Fully Paid"` if balance ≤ 0; else `"Outstanding Balance"` |
| `has_accepted_payment` | True if any accepted payment exists |
| `pending_payment` | The single pending payment, if any |
| `can_accept_additional_payment` | No pending claim, and not fully paid (balance > 0 or no agreed total) |

**Phase gate:** moving `job_request` → `pending_edit` requires `has_accepted_payment` (server-enforced; UI disables the advance button with reason).

### 6.7 `orders.OrderPhaseChange`

| Field | Type | Notes |
| --- | --- | --- |
| order | FK → Order | CASCADE; `related_name=phase_changes` |
| from_status / to_status | CharField | Same choices as `Order.status` |
| changed_by | FK → User | SET_NULL; staff who advanced |
| changed_at | DateTime | Indexed; set on create (seed spreads over last 60 days) |

A row is written on every successful `advance_order_phase` POST (in addition to `ActivityLog(PHASE_MOVED)`).

### 6.8 `orders.Payment`

| Field | Type | Notes |
| --- | --- | --- |
| order | FK | CASCADE |
| channel | FK → PaymentChannel | PROTECT; nullable for manual adj. |
| amount_claimed | Decimal | Customer claim or staff entry |
| proof_file | FileField | `payment_proofs/` (images shrunk/sanitized on upload) |
| status | TextChoices | `pending` \| `accepted` \| `rejected` (default pending) |
| rejection_reason | CharField | Optional short reason on reject |
| reviewed_by / reviewed_at | FK / DateTime | Set when staff accept/reject |
| is_manual_adjustment | Boolean | True when staff adds from accounting |
| note | CharField | |
| recorded_by | FK → User | Staff who recorded manual payment |
| created_at | DateTime | |

**Rules**

- Customer submit + later order-page uploads create **pending** claims.
- Manual accounting adjustments (admin, or staff with accounting-edit) are **accepted** automatically (`reviewed_by` / `reviewed_at` set).
- Only **pending** payments can be reviewed; accepted/rejected are final in this batch.
- At most one pending payment per order (`UniqueConstraint` on `order` where `status=pending`).
- Many payments per order are allowed (history of accepted/rejected + one pending).

### 6.9 `sales.Lead`

| Field | Type | Notes |
| --- | --- | --- |
| customer | FK → User | CASCADE |
| order | OneToOne → Order | CASCADE |
| stage | TextChoices | See below |
| created_at | DateTime | |

**Stages:** `new_lead` → `order_confirmed` → `design_review` → `approved` → `completed` \| `lost`  
(Staff can set any valid stage; not a forced linear FSM in code.)

### 6.10 Apps without models

- `apps.accounting` — views/forms only
- `apps.core` — no persistent models

### 6.11 Django admin registrations

| Model | App admin highlights |
| --- | --- |
| User | Email-centric UserAdmin; role & accounting flag |
| Design | List + ownership |
| ActivityLog | Kind, relations, time |
| PaymentChannel | Kind, active |
| Order | order_id, status, totals |
| OrderPhaseChange | from/to status, changed_by, time |
| Payment | Order, channel, amount |
| Lead | Customer, order, stage |

---

## 7. Authentication & authorization

### 7.1 Authentication flow

```
Signup (email + password [+ optional phone])
    → EmailAddress created
    → Mandatory verification (console email in DEV)
    → Confirm link → login capable

Login (email)
    → AccountAdapter.get_login_redirect_url
         staff/admin → /staff/
         customer    → /app/

Logout (GET allowed: ACCOUNT_LOGOUT_ON_GET=True)
    → /
```

**allauth settings highlights**

- `ACCOUNT_LOGIN_METHODS = {"email"}`
- `ACCOUNT_USER_MODEL_USERNAME_FIELD = None`
- `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`
- `ACCOUNT_ADAPTER = apps.accounts.adapters.AccountAdapter`
- `ACCOUNT_FORMS["signup"] = BlytzSignupForm`

**Backends:** `ModelBackend` + `allauth.account.auth_backends.AuthenticationBackend`

### 7.2 Authorization matrix

| Capability | Customer | Staff | Staff + accounting | Admin |
| --- | --- | --- | --- | --- |
| `/app/` designs & orders | ✓ | ✗ | ✗ | ✗ |
| `/app/profile/` | ✓ | ✓ | ✓ | ✓ |
| `/staff/` overview, jobs, sales | ✗ | ✓ | ✓ | ✓ |
| Accounting **view** | ✗ | ✓ | ✓ | ✓ |
| Accounting **edit** (set total / add payment) | ✗ | ✗ | ✓ | ✓ |
| Review payment claims (accept/reject) | ✗ | ✓ | ✓ | ✓ |
| Payment channels CRUD | ✗ | ✗ | ✗ | ✓ |
| User management | ✗ | ✗ | ✗ | ✓ |
| `/staff/admin-only/` | ✗ | ✗ | ✗ | ✓ |
| Django `/admin/` | via Django flags | typically staff | | typically superuser |

**Enforcement**

- Function views: `@customer_required`, `@staff_required`, `@admin_required` (login + role; else `PermissionDenied` → 403)
- Class views: matching mixins in `apps.accounts.mixins`
- Accounting POST additionally checks `user.can_edit_accounting_page()`
- Payment review does **not** require accounting-edit; any staff/admin may accept/reject
- Design/order customer views filter by `owner` / `customer=request.user`
- Role changes apply on the user’s **next request** (session user reloaded from DB)

---

## 8. URL map & request routing

Root `config/urls.py` includes:

| Include | Prefix |
| --- | --- |
| Django admin | `/admin/` |
| allauth | `/accounts/` |
| designs, orders, accounting, sales, accounts, core | `` (app-defined paths) |

DEBUG only: `static()` for media; core component gallery routes.

### 8.1 Public / auth

| Path | Name | Access |
| --- | --- | --- |
| `/` | `home` | Public (anonymous). Logged-in customer → `/app/`; staff/admin → `/staff/` |
| `/accounts/signup/` | allauth | Public |
| `/accounts/login/` | allauth | Public |
| `/accounts/logout/` | allauth | Auth |
| `/accounts/confirm-email/`… | allauth | Public |

### 8.2 Customer (`/app/`)

| Path | Name | Method | Purpose |
| --- | --- | --- | --- |
| `/app/` | `app_home` | GET | Dashboard |
| `/app/profile/` | `account_profile` | GET/POST | Profile |
| `/app/designs/` | `design_list` | GET | Designs |
| `/app/designs/new/` | `design_create` | POST | Create draft → editor |
| `/app/designs/<id>/` | `design_detail` | GET | Redirects to editor |
| `/app/designs/<id>/editor/` | `design_editor` | GET | Editor + payment modal data |
| `/app/designs/<id>/save/` | `design_save` | POST | Save canvas (HTML or JSON) |
| `/app/designs/<id>/submit/` | `design_submit` | POST | Submit + payment (HTML or JSON) |
| `/app/designs/<id>/ai/suggest/` | `design_ai_suggest` | POST | Stage O: two Gemini design candidates (JSON); never mutates `Design` |
| `/app/orders/` | `order_list` | GET | Customer submission history (Orders): own Orders only, paginated |
| `/app/orders/<order_id>/` | `order_detail` | GET/POST | Order detail + payment history + additional proof upload + final design preview/approve |
| `/app/orders/<order_id>/approve-final-design/` | `approve_final_design` | Customer POST | Approve final design (version must match); owner only; Pending Edit only |

### 8.3 Staff / admin (`/staff/`)

| Path | Name | Access | Purpose |
| --- | --- | --- | --- |
| `/staff/` | `staff_home` | Staff+ | Overview stats + charts (customers 403) |
| `/staff/jobs/` | `jobs_pipeline` | Staff+ | Jobs kanban (`q`, `customer`, `pending_review=1` filters) |
| `/staff/orders/<order_id>/` | `staff_order_detail` | Staff+ | Order ops; job status + payment status badges; mock-ups; garment/design details from `canvas_json_snapshot` (does not write `Design.canvas_json`); final design (Pending Edit); payment proofs + review in all phases; phase history |
| `/staff/orders/<order_id>/previews/<side>/download/` | `download_order_preview` | Staff+ GET | Full-res front/back mock-up PNG download |
| `/staff/orders/<order_id>/final-design/` | `upload_final_design` | Staff+ POST | Upload/replace final design (Pending Edit only); bumps version; no history |
| `/staff/orders/<order_id>/advance/` | `advance_order_phase` | Staff+ POST | Next phase only (gate: accepted payment before Pending Edit); records `OrderPhaseChange` |
| `/staff/orders/<order_id>/payments/<id>/review/` | `review_payment` | Staff+ POST | Accept or reject pending payment |
| `/staff/accounting/` | `accounting_list` | Staff+ | Accounting list + charts (accepted payments only; customers 403) + CSV export form |
| `/staff/accounting/export.csv` | `accounting_export_csv` | Staff+ GET | Read-only orders CSV (job status ≠ payment status); optional `status`, `date_from`, `date_to`, `pending_review`; customers 403; no source mutations |
| `/staff/accounting/<order_id>/` | `accounting_detail` | Staff+ | Detail; POST if can edit |
| `/staff/sales/` | `sales_pipeline` | Staff+ | Leads; `?tab=incomplete` |
| `/staff/sales/<lead_id>/` | `lead_detail` | Staff+ | Lead + timeline |
| `/staff/sales/<lead_id>/stage/` | `update_lead_stage` | Staff+ POST | Change stage |
| `/staff/payment-channels/` | `payment_channel_list` | Admin | Channels |
| `/staff/payment-channels/add/` | `payment_channel_create` | Admin | Create |
| `/staff/payment-channels/<id>/edit/` | `payment_channel_edit` | Admin | Edit |
| `/staff/payment-channels/<id>/deactivate/` | `payment_channel_deactivate` | Admin POST | Soft deactivate |
| `/staff/users/` | `user_manage_list` | Admin | Users |
| `/staff/users/add/` | `user_create_staff` | Admin | Create staff |
| `/staff/users/<id>/` | `user_edit` | Admin | Role / flags |
| `/staff/admin-only/` | `staff_admin_only` | Admin | Smoke page |

### 8.4 Dev-only

| Path | Purpose |
| --- | --- |
| `/dev/components/` | Design-system gallery |
| `/dev/components/customer/` | Customer chrome gallery |
| `/dev/components/staff/` | Staff chrome gallery |

---

## 9. Core business workflows

### 9.1 Customer: create → save → submit

```
POST /app/designs/new/
  → Design(title=Untitled, garment_template=tee, canvas_json={version:1, objects:[]})
  → ActivityLog(DESIGN_CREATED)
  → redirect editor

POST /app/designs/<id>/save/
  → reject if design already has an Order (clear error; no canvas/title change)
  → DesignSaveForm(canvas_json, optional title; empty/whitespace title → "Untitled design")
  → last save wins (no conflict check)
  → JSON {ok:true, title, updated_at} if Accept/XHR else redirect

POST /app/designs/<id>/submit/   [atomic + design-row writer lock + unique Order.design]
  guards: not already submitted (pre-check + re-check after the writer lock);
          form valid; payment window not expired;
          front + back preview PNGs validated (Pillow)
  → update design.canvas_json (+ optional garment fields)
  → Order(status=job_request, canvas_json_snapshot=…,
          preview_image, preview_back_image)
  → Payment(channel, amount_claimed, proof_file, status=pending)
  → Lead(stage=new_lead)
  → ActivityLog(DESIGN_SUBMITTED + ORDER_CONFIRMED)
  → redirect order detail (JSON {ok, redirect} for XHR)
  → already-submitted / lock race → JSON {ok:false, errors.design} for XHR
```

**Submit previews (client)** — Stage I

1. On payment-form submit, `editor_page.js` blocks the native POST; **re-checks** readiness; refuses if `saveInFlight` / `submitInFlight`.
2. Snapshots intended design via `preparePersistPayload` + persist **fingerprint**; sets `submitInFlight` / `submitGeneration`.
3. Renders both views with `BlytzEditor.renderFrozenPreview({ envelope, view, garment })`. `envelope` is `JSON.parse` of the `preparePersistPayload` string that will be posted. `garment` is a copy of template/color taken at the same time. This does **not** call `getPreviewPNG` and does **not** call `loadCanvasJSON` on the live editor.
4. Each frozen view is loaded on a temporary `fabric.StaticCanvas` (disposed on success and failure). Artwork object count must match the frozen payload or the render rejects. The PNG is composited **800×800**: UNDER garment → that artwork → OVER garment (print-area guides omitted). Garment SVGs use the snapshotted template/color. CSS `var(--…)` references are baked to hex. Grain opacity is lowered, and grain is stripped on a retry that uses the **same** frozen payload. Files must stay ≤ **5 MB** (`services/preview_images.py` on the server). A render failure blocks the POST and shows that error when it is one of the known preview messages.
5. After previews: abort if the live fingerprint no longer matches (an edit during submit is not posted). Otherwise POST the frozen `canvas_json`, the snapshotted garment fields, and the two PNGs. A newer `submitGeneration` drops a stale result and does not POST it.
6. **Success only** after server JSON `{ ok: true, redirect }` — then `allowUnloadOnce` + navigate. Failures clear the submit lock; unclear network responses warn to check Orders before retrying.
7. Preview modal remains presentation-only (Stage H/H.1); cancel is blocked while submit is in flight.

**Payment window** (initial submit only)

1. Client opens payment modal → records `window_started_at` (ISO datetime).
2. Countdown = `PAYMENT_WINDOW_MINUTES` (default 10).
3. Server rejects submit if `now > window_started_at + PAYMENT_WINDOW_MINUTES`.
4. Future start timestamps (> now + 1 minute) rejected by form.

**Proof file rules** (client + server; setting `PROOF_MAX_UPLOAD_MB`, default 15)

- Extensions: `.png`, `.jpg`, `.jpeg`, `.pdf`
- Max size: `PROOF_MAX_UPLOAD_MB` MB (browser check, form validator, messages, tests)
- Content types checked when present
- Images: verified, EXIF-oriented, metadata stripped, longest side ≤ 2000 px, PNG optimized / JPEG ~q85 via `services.proof_images`
- PDFs stored as uploaded; corrupt/fake images rejected with a friendly message

**Later uploads** (customer order page, any phase including Completed)

- Show history table (amount, channel, date, status, rejection reason).
- Upload form when no pending payment and (balance > 0 **or** no agreed total).
- If pending → “Payment awaiting staff review”; if fully paid → “Fully paid” (no form).
- POST uses `transaction.atomic` + `select_for_update` on the order; unique pending constraint as a race backstop.

### 9.1b Customer submission history (Stage J)

Route: `GET /app/orders/` (`order_list`) — nav label **Orders**. Reuses the existing Order list; does **not** add a second tracking model.

| Concern | Source of truth |
| --- | --- |
| Who submitted | `Order.customer` (= authenticated user filter) |
| When submitted | `Order.created_at` |
| Design title / garment | `Order.design.title`, `design.garment_template`, `design.garment_color` (labels via `format_garment_display`) |
| Job status | `Order.status` (display via `customer_order_status_label`; unknown values → `Unknown status (…)` with warning badge — never mapped to Completed/Paid) |
| Thumbnail | Existing `Order.preview_image` when present; otherwise a “No preview” placeholder (no new rasterization) |
| Detail | Link to `order_detail` (`order_id` + `customer=request.user`) |

**Ownership:** `@customer_required`; queryset `Order.objects.filter(customer=request.user)`. Detail stays `get_object_or_404(..., customer=request.user)` → 404 for other customers. Drafts without an Order are omitted.

**Pagination:** Django `Paginator`, `ORDERS_PER_PAGE` = 20 (`apps.orders.customer_display`).

**Tests:** `apps.orders.tests.test_order_list`; ownership also covered in `apps.designs.tests.test_ownership`.

### 9.2 Staff: jobs pipeline + payment review

Customers submit; staff/admin review. Phase advances never mutate `Design.canvas_json` (inspection uses frozen `Order.canvas_json_snapshot` + stored mock-ups).

```
GET /staff/jobs/?q=&customer=
  → columns by Order.status (job phase)
  → cards show payment_status (Fully Paid / Outstanding) separately from column phase
  → cards show “Payment awaiting review” when pending_payment exists

GET /staff/orders/<id>/
  → job status stepper + payment_status badge (separate from phase)
  → garment template/color, customer, notes, design details from snapshot
  → front/back mock-ups (lightbox + download); payment proofs in Job Request and Pending Edit layouts

POST /staff/orders/<id>/advance/
  → if next is pending_edit and not has_accepted_payment → reject (message + disabled UI)
  → else status = next in PHASE_FLOW only (ignores client target)
  → OrderPhaseChange(from, to, changed_by)
  → ActivityLog(PHASE_MOVED)
  → does not alter Design.canvas_json or order preview files

GET /staff/orders/<id>/previews/<front|back>/download/
  → staff/admin only; attachment PNG (customers 403)

POST /staff/orders/<id>/payments/<payment_id>/review/
  → action=accept|reject (optional rejection_reason)
  → any staff/admin; only pending payments; reviewed payments are final
```

### 9.2b Pending Edit: final design upload & customer approval

```
Staff (Pending Edit only):
  GET /staff/orders/<id>/
    → two-column layout on landscape tablets/laptops (`md:landscape:grid-cols-2`)
       LEFT: customer, payments, mock-up previews
       RIGHT: final design preview + upload/replace form
    → stack to one column on phones / portrait tablets
    → “Move to Production” always available; browser confirm if no final design yet

  POST /staff/orders/<id>/final-design/
    → validate png/jpg/jpeg/pdf ≤ PROOF_MAX_UPLOAD_MB (no shrink/alter)
    → delete previous file if any; store new file; final_design_version += 1
    → ActivityLog(DESIGN_REVISED) when version > 1
    → customers 403

Customer:
  GET /app/orders/<id>/
    → shows final design as soon as uploaded (image preview or PDF download link)
    → “Approve final design” only while status=pending_edit and a final design exists

  POST /app/orders/<id>/approve-final-design/  {version}
    → owner only (other customers 403); staff 403 (@customer_required)
    → reject if status ≠ pending_edit or version ≠ final_design_version
       message: "The design was updated. Please review the new version."
    → else approved_version / approved_at; status → production
    → OrderPhaseChange + ActivityLog(DESIGN_APPROVED)
```

Sales Pipeline lead stages are unchanged.

### 9.2c Staff overview charts (`/staff/`)

```
GET /staff/   [@staff_required — customers 403]
  → json_script payloads (no public JSON endpoint required)
  → bar: orders per phase (Job Request → Completed)
  → line: new orders per day (last 30 days, by Order.created_at)
  → tile: pending Payment count → /staff/jobs/?pending_review=1
  → each chart: empty state "No data yet" + <details> data table fallback
  → Chart.js + staff_charts.js; prefers-reduced-motion disables animation
```

Helpers: `apps.accounts.dashboard` (`orders_by_phase_chart`, `new_orders_per_day_chart`, `payments_awaiting_review_count`).

### 9.3 Staff: accounting

```
GET list → sum total_paid (accepted only), sum positive balances
         → pending-payment marker per order
         → charts (accepted payments only):
              doughnut: collected vs outstanding
              line: collections over time (30 days, Payment.created_at)
              doughnut: payments by channel (GCash / Maya / Bank [+ Other])
         → json_script + empty states + table fallbacks (same chart helper)
         → export form → GET /staff/accounting/export.csv

GET export.csv [@staff_required — customers 403]
  → read-only CSV of orders (staff/admin sink; does not write Order/Payment/Design)
  → columns: order_id, created_at, customer, design title, garment label,
              job_status (Order.Status label), payment_status (Fully Paid /
              Outstanding Balance), agreed/paid/balance, payment_awaiting_review
  → filters: status (job phase), date_from / date_to (YYYY-MM-DD on created_at),
              pending_review=1; invalid filters → 400; empty match → header only

POST detail action=set_total
  → agreed_total + accounting_edited_*

POST detail action=add_payment
  → Payment(is_manual_adjustment=True, status=accepted, reviewed_by=user, …)
```

Helpers: `apps.accounting.charts`. View-only staff see forms disabled / POST raises `PermissionDenied`. Payment status is visible to all staff. No charts on Sales Pipeline yet. No XLSX/PDF tabular reports (CSV + artwork PNG downloads only).

### 9.4 Staff: sales

```
Lead created automatically on design submit

Pipeline:
  - stage columns for all Lead.Stage values
  - tab=incomplete → Designs with no related Order

POST stage update → ActivityLog(LEAD_STAGE_CHANGED)
Lead detail → ActivityLog filter by customer
```

### 9.5 Messenger deep-link

- Env: `MESSENGER_PAGE_USERNAME`
- Context: `messenger_url = https://m.me/{username}`
- Used on public/customer surfaces for checkout support (no chat API)

---

## 10. Frontend & UI architecture

### 10.1 Template bases

| Base | Audience |
| --- | --- |
| `base.html` | Shared shell |
| `base_public.html` | Landing, marketing |
| `base_customer.html` | `/app/` |
| `base_staff.html` | `/staff/` |
| `account/base_account.html` | allauth screens |

Nav partials: `navbar_public.html`, `navbar_customer.html`, `navbar_staff.html`.

- Customer/staff navs have no “Home” link; the logo links to `/app/` or `/staff/` respectively.
- Staff navbar shows a role badge from `user.get_role_display()`: **Admin** = filled black (`bg-ink`) with white text (canvas ring for contrast on the dark bar); **Staff** = outlined. No user name in the navbar.
- Logout still lands on `/` (public landing).

### 10.2 Design system components (`templates/components/`)

Includes (non-exhaustive): `badge`, `breadcrumbs`, `button`, `card` (+ open/close), `drawer`, `empty_state`, `error_state`, `file_input`, `footer`, `input`, `loading_state`, `messages`, `modal`, `pipeline_card`, `select`, `stat_tile`, `stepper`, `table`, `tabs`.

**Message banners** (`components/messages.html` + `static/js/ui.js`): shared across all bases/roles. Fixed below the navbar (`--blytz-nav-offset`, z-index 60 so clicks are not trapped under the sticky nav). Polite live region. Every banner has a close button (document-level click delegation). Success banners auto-dismiss after 2s (timer pauses on hover/focus); error and warning stay until closed. With `prefers-reduced-motion`, dismiss skips the fade. Order confirmation still shows `order_id` on the order detail page because the success banner fades.

Gallery at `/dev/components/` when `DEBUG=True`.

### 10.3 Brand / Tailwind tokens

Defined in `docs/PROJECT_BRIEF.md` and `src/styles/main.css` (`@theme`):

| Token | Hex | Role |
| --- | --- | --- |
| `ink` | `#0A0A0A` | Text, primary actions |
| `ink-muted` | `#525252` | Secondary text |
| `ink-subtle` | `#737373` | Hints |
| `canvas` | `#FFFFFF` | Page background |
| `surface` | `#FAFAFA` | Soft panels |
| `border` / `border-strong` | `#E5E5E5` / `#0A0A0A` | Borders |
| `gold` / `gold-soft` | `#C9A227` / `#F7F1DE` | Optional accent only — never primary fill |
| `danger` / `success` / `warning` | status colors | |

Typography: `font-display` (Playfair Display), `font-sans` (GitHub-style system stack).  
Focus: `focus-visible:outline-ink`. Mobile-first. Global skip link (`.blytz-skip-link` → `#main`) in `base.html` for keyboard users.

### 10.4 Client JavaScript (`static/js/`)

| File | Role |
| --- | --- |
| `editor_contract.js` | `window.BlytzEditor` public API |
| `editor_canvas.js` | Fabric workspace + schema helpers |
| `ai_chat.js` | Stage O AI Assistant (Gemini when configured; Stage 2 mock fallback; two-candidate preview/commit) |
| `vendor/fabric/fabric.min.js` | Fabric.js 6.6.1 (local) |
| `editor_page.js` | Save-state (Stage G), design preview/review (Stage H), navigation guards, payment modal, submit + preview PNG upload, CSRF |
| `editor_chrome.js` | Phone/tablet chrome: layout mode (`sheets` vs docked), contextual selection bar, undo/redo buttons, `visualViewport` keyboard inset |
| `payment_details.js` | Channel account/QR + Copy buttons; shared proof size check |
| `payment_upload.js` | Customer order-page additional proof upload (full-screen sheet on phones) |
| `staff_preview_viewer.js` | Staff mock-up lightbox (pinch/scroll zoom) |
| `staff_charts.js` | Chart.js helper (B&W/gray theme, empty states, reduced-motion) |
| `nav.js` | Navigation behavior (incl. jobs pipeline mobile tabs) |
| `ui.js` | Shared UI helpers |
| `demo-widget.js` | Demo/helper widget |

Vendored: `static/vendor/fabric/` (editor), `static/vendor/chartjs/` (Chart.js 4.4.6 UMD — staff charts only; no CDN).

Additional CSS: `static/css/responsive.css`; compiled Tailwind → `static/css/tailwind.css` (gitignored; rebuild with `tailwind build`).

### 10.5 Responsive layout (non-editor + editor)

| Surface | Behavior |
| --- | --- |
| Staff Pending Edit / order detail | One column on phones & portrait tablets; two columns on landscape tablets (`md:landscape:grid-cols-2`) and laptops |
| Jobs Pipeline | Tabs &lt;768px; horizontal snap-scroll on tablet **portrait**; 2×2 grid on tablet **landscape** (768–1279); four columns ≥1280 |
| Data tables | `.table-responsive-cards` stacks to labeled cards ≤767px |
| Charts | `w-full` + Chart.js `responsive: true`; table fallbacks in `<details>` |
| Payment modal / order upload | Full-screen sheet on phones (`100dvh` + safe-area); large Copy targets; proof `accept` includes `image/*` + `capture="environment"` for camera/screenshots |
| Touch targets | `@media (pointer: coarse)` enlarges buttons/inputs (≥2.75rem) — input **type**, not width alone |
| Viewport units | Prefer `100dvh` (never `100vh`); safe-area insets on nav, sheets, editor toolbar |
| Image viewers | Staff mock-up lightbox supports pinch-zoom |

**Editor chrome**

| Viewport | Chrome |
| --- | --- |
| Phone (&lt;768) | Top: title, Undo, Redo, Save, Submit. Bottom: Text, Image, Garment, AI, Layers (+ Front/Back). Tool panels as bottom sheets; AI as full-screen sheet. Contextual bar (color / duplicate / forward / back / delete) above the bottom toolbar. Text edited in Text sheet input (`visualViewport` raises the sheet). |
| Landscape tablet + `(pointer: coarse)` + width ≥900 | Docked side panel ~300–340px (`data-editor-layout="docked"`), collapsible; not width-alone |
| Touch canvas | Fabric `touchCornerSize` enlarged on coarse pointers; `touch-action: none`; one finger moves objects; two fingers pinch-zoom/pan (0.35×–4×). Desktop: zoom chrome (− / % / +) + Ctrl/Cmd+wheel toward cursor; Ctrl/Cmd+=/−/0 when focus is in the editor. When zoom &gt; 100%: **Space+drag** or **middle-button drag** pans via `panSceneBy` (grab/grabbing cursor; Fabric selection suppressed; not undoable). **Option A viewport zoom:** CSS `translate+scale` on shared `#editor-artboard-scene` (garment under + Fabric `.canvas-container` + garment over). Fabric `viewportTransform` stays **identity** (no per-layer VPT copy). `#editor-print-overflow-warning` is a wrap sibling (not scaled). Hit-testing relies on Fabric mapping via `getBoundingClientRect` (includes ancestor CSS transforms). Logical 800×800 / overflow / undo unchanged. Zoom **preserved** across Front/Back; **reset to 100%** on responsive CSS resize. Twin: `apps/designs/canvas_zoom.py` (`scene_zoom_to_point`, glued invariant). Imported images downscale to ≤**2000** px longest edge. Orientation change reflows canvas size without clearing selection or unsaved edits. |

---

## 11. Design editor contract

The Fabric.js canvas implementation honors this **stable public API** on `window.BlytzEditor`:

| Method | Behavior |
| --- | --- |
| `getCanvasJSON()` | Return current canvas object (Blytz schema envelope) |
| `loadCanvasJSON(json\|string)` | Load state into editor |
| `getPreviewPNG(opts?)` | PNG data-URL of the logical 800×800 workspace. No opts: sync, active view, artwork only. `{ view, includeGarment }` returns a Promise; with `includeGarment: true` composites UNDER + artwork + OVER (CSS vars baked to hex; print guides omitted; inactive view offscreen — no live switch / commits) |
| `onCommittedChange(cb)` | Subscribe to commits; returns unsubscribe |
| `validateCanvasJSON(json)` | Validate Blytz schema v1 envelope (no mutation) |
| `applyCanvasJSON(json)` / `previewCanvasJSON(json)` | Safe validate → snapshot → load; restore on failure; loads do not fire commit listeners |
| `undo()` / `redo()` / `canUndo()` / `canRedo()` | **Additive** history helpers for phone chrome (envelope snapshots; does not change saved JSON schema) |

### 11.1 Client modules

| File | Role |
| --- | --- |
| `static/vendor/fabric/fabric.min.js` | Fabric.js **6.6.1** UMD browser build (MIT; see `LICENSE`) |
| `static/js/editor_canvas.js` | Fabric workspace, B1 views, safety scan, image pipeline, commits |
| `static/js/editor_garments.js` | Inline SVG garments (under/over split), colors, print areas, `renderGarmentLayer`, `resolveSvgCssVars` / `getExportLayerMarkups` (PNG export), contrast helpers |
| `static/garments/` | `tee` / `polo` / `hoodie` / `jersey` × front/back SVGs + `garments.json` (labels, print areas) |
| `static/js/editor_tools.js` | Upload / Elements / Layers / Garment panels, shape factories |
| `static/js/editor_properties.js` | Properties sheet, clamps, Edit pill, ≤1279 exclusivity |
| `static/js/editor_contract.js` | `window.BlytzEditor` public API |
| `static/js/ai_chat.js` | Two-candidate AI chat (live suggest + mock fallback) |
| `static/js/editor_page.js` | Save-state, navigation guards, payment modal, submit validation, CSRF |
| `apps/designs/canvas_safety.py` | Server twin of `scanCanvasPayload` (v1 only) |
| `apps/designs/garment_choices.py` | Template/color allow-lists, template aliases, stale-client views guard |
| `qa/` | Console-paste GATE / regression / garment scripts + device checklist |

`editor_page.js` wires:

- Initial load from `data-canvas-json` on the editor root
- Inline editable title (`data-editor-title`) for drafts only; included in Save POST; crumb + `document.title` update on success
- Save POST with `canvas_json`, optional `title`, optional `garment_template` / `garment_color`, and CSRF cookie
- Submit modal: channel, amount, proof, `window_started_at`, canvas snapshot, garment fields, front/back preview PNGs (required)
- Disables submit when window expired or design already submitted; submitted designs show a read-only title
- Submit generates front + back mock-ups via `getPreviewPNG({ view, includeGarment: true })`; failure blocks the request

### 11.1a Save-state reliability (Stage G)

Document dirty state is derived by comparing a **persist fingerprint** (stable `JSON.stringify` of `{ canvas, title, garment_template, garment_color }`) to the last successfully saved fingerprint — not an independent boolean that can drift.

| Concern | Behavior |
| --- | --- |
| Mark dirty | `onCommittedChange` (canvas), `onGarmentChange`, title `input`/`change`, and `onHistoryNavigate` (undo/redo after restore) recompute vs last saved |
| Not dirty | Selection changes, Properties open/tabs, hover, `clearSelection`, live `runSilent` previews, uncommitted curve preview (`isCurvePreviewDirty` skips recompute; `discardCurvePreview` restores then recomputes) |
| Saved | Only after HTTP JSON `{ ok: true }` for the fingerprint that was POSTed; then recompute vs **live** canvas — if the user edited during the in-flight save, status returns to **Unsaved changes** |
| Saving | Entered only when a save request actually begins; single in-flight mutex (`saveInFlight` / generation) prevents concurrent POSTs |
| Save failed | Network / non-OK / malformed JSON / form errors → **Save failed** with message; latest local work kept; Save retries the same pathway |
| UI | `[data-editor-save-status]` (aria-live, deduped announcements) + ephemeral `[data-editor-status]` for flow messages; Design info → **Before you submit** (`[data-editor-readiness]`) |
| Navigation | Native `beforeunload` when genuinely dirty (browser text only). In-editor breadcrumb/`a[href]` clicks confirm before leave. Submit success redirect and intentional unload use `allowUnloadOnce`. Does not intercept unrelated site navigation outside the editor shell |
| Readiness checks | Client review only: draft not submitted, `canPersist`, no save in flight, no submit in flight, non-destructive envelope size ≤ 2 MiB, artwork object count (advisory — server does **not** require artwork), payment channels present, payment fields noted as modal/server. **Does not** call `preparePersistPayload` (would discard curve preview). Server validation remains authoritative; readiness never bypasses CSRF, ownership, window, proof, or preview PNG rules |
| Probe API | `window.BlytzEditorSaveState` (`isDirty`, `getStatus`, `isSubmitInFlight`, `getSubmissionReadiness`, `shouldWarnUnload`, …) for QA — does not replace `canPersist` locks |
| History hook | `BlytzEditor.onHistoryNavigate` fires after undo/redo restore so dirty can match last saved when the user undoes back to that snapshot |

**Unchanged:** schema allowlists, 2 MiB cap, auth/ownership, CSRF form field on save, submit transaction + payment window, no autosave service, no new endpoints.

### 11.1c Submission workflow hardening (Stage I)

Invariant: a successful submission persists a **server-validated snapshot** of the exact intended client design state (from `preparePersistPayload`), not stale/partial UI state.

| Layer | Protection |
| --- | --- |
| **Client** | Re-check `getSubmissionReadiness` at Submit click and at payment-form send; `submitInFlight` + `submitGeneration` prevent overlapping preview/POST; save blocked while submitting; fingerprint of the snapshotted payload must still match the live design after async preview gen or the POST is not sent; Front/Back PNGs are rendered from that frozen envelope (`renderFrozenPreview`), not from a later live-canvas raster; POST sends that `canvas_json` plus the snapshotted garment template/color; statuses: Generating previews → Submitting → navigate only on `{ok, redirect}` / failure clears lock; cancel blocked during in-flight submit; `allowUnloadOnce` only after confirmed success |
| **Server** | Auth + ownership (`owner=request.user`); CSRF; independent `DesignSubmitForm` validation (canvas schema/safety, proof, preview PNGs, window, amount, channel) — does **not** trust client ready/saved flags. Inside `transaction.atomic`: `UPDATE` the design row first (this is what takes SQLite’s writer lock; MySQL row locking was not run here), then `select_for_update()` and re-check `is_submitted`. `select_for_update()` does **not** emit `FOR UPDATE` on this project's SQLite backend (`has_select_for_update` is false). `Order.design` is still a `ForeignKey` (`related_name="orders"`); migration `orders.0006_unique_order_per_design` adds `UniqueConstraint` `unique_order_per_design`. A losing insert or database lock returns the existing already-submitted JSON when an order for that design is visible, otherwise a generic retry message with no database text. One lock-error retry runs inside the view |
| **Database** | Dev and the Django test runner use SQLite (`DATABASE_URL` is unset in `.env`; test DB is `file:memorydb_default?mode=memory&cache=shared`). MySQL via `DATABASE_URL` is documented as optional and was **not** configured or tested here. Before `0006`, `db.sqlite3` had 10 orders and no design with more than one order. Code and seed data treat a second order for the same design as invalid (`is_submitted` is `orders.exists()`; save/submit stop; `seed_demo` uses `get_or_create(design=…)`). The constraint does not change the reverse relation to a `OneToOneField` |

**Tests:** `apps.designs.tests.test_submit` (sequential second submit, XHR already-submitted, snapshot persistence); `apps.designs.tests.test_submit_workflow` (source contracts); `apps.designs.tests.test_submit_concurrency` (SQLite: no `FOR UPDATE` in the query; second `Order` for one design raises `IntegrityError`; two threads / two connections persist one order). Browser: `qa/stage_i_verify.js` (Stage I) and `qa/stage_i1_verify.js` (frozen preview, live-edit block, dispose, Stage H blob preview).

**Concurrency not claimed:** MySQL/PostgreSQL row locks were not executed. On SQLite, overlapping submits are serialized by the design-row `UPDATE` plus the unique index. A loser can receive “Please try again.” if it observes `database is locked` before the winner’s commit is visible; the test then confirmed a following submit gets “already submitted” and the order count stays 1. Pixel identity between a live canvas and a reload of its JSON was checked for a solid red rectangle on a white tee, not for every Fabric feature (fonts, filters, grain).

**Stage H vs submit:** The Preview modal still calls `getPreviewPNG`. That path rasters the **live** canvas for the active view (and an offscreen clone for the other view). Submit does not use that path.

**Unchanged:** Stage G save-state, Stage H/H.1 preview presentation-only, 2 MiB / proof / preview PNG limits, payment window, no AI / new external services.

### 11.1b Customer design preview / final review (Stage H / H.1)

Customer-facing **Preview** in the editor opens `#design-preview-modal` for a garment + artwork mock-up and a save-state-aware review panel. Presentation-only: does **not** mutate the live Fabric canvas, history, selection, dirty fingerprint, Front/Back active view, title, or garment.

| Concern | Behavior |
| --- | --- |
| Entry / exit | Top-bar **Preview** (`data-editor-preview`); **Back to edit** / backdrop / × / Escape close and restore focus; focus trap while open |
| Mock-up | `BlytzEditor.getPreviewPNG({ view, includeGarment: true })` for Front and Back. The active view is rastered from the live canvas (selection handles are discarded for the PNG, then the prior active object is restored); the other view uses an offscreen `StaticCanvas`. UNDER→art→OVER compositing matches export, but this is **not** the submit path (`renderFrozenPreview` from the frozen envelope). Stale async responses ignored via `previewRequestGen`; blob/object URLs revoked on replace/close; closed-preview callbacks noop |
| Review data | Title, garment label/color, preview side, **save status**, and readiness from `BlytzEditorSaveState` / `getSubmissionReadiness` (no invented readiness rules) |
| Render vs save | `previewRenderStatus` (`idle`/`loading`/`ready`/`error`) is separate from Stage G `saveUiStatus`. Loading/honesty copy never presents a stale image as a newly confirmed saved mock-up without an update in progress or error |
| Save-triggered refresh (H.1) | On **clean** `performSave` SUCCESS (fingerprint still matches live), if the preview modal is open, re-render the **current** preview side via `getPreviewPNG` while keeping the modal open. Prior image stays until the new render arrives. Failed save → no refresh-as-saved. Already-saved Preview **Save** skips a redundant `performSave` (no save loop) |
| Refresh failure | Save remains **Saved**; show in-modal preview-refresh error + **Retry mock-up**; do not blank the prior image or mark save failed |
| Honesty | Unsaved / saving / save-failed copy never presents a draft as a saved final; post-save refresh loading/error copy is explicit |
| Save / Submit | Preview **Save** calls existing `performSave` only (no duplicate save path). No nested payment/submit — user returns to editor **Submit** |
| Races | `previewRequestGen` + fingerprint match; Front/Back switches and close/reopen invalidate in-flight work; edits during refresh that dirty the design abort applying a “saved” image |
| Probe API | `window.BlytzEditorDesignPreview` (`open` / `close` / `setSide` / `getRenderStatus` / `refreshAfterSave` / …) for QA |
| Tests | `apps.designs.tests.test_design_preview` (source + ownership/save contracts); browser: `qa/stage_h_verify.js` (incl. post-save image refresh while modal open) |

**Unchanged:** canvas safety, 2 MiB cap, CSRF, ownership, submission locks, Stage G save-state machine, no new backend routes/migrations/AI/payment.

**Limitations:** post-save refresh re-exports the client canvas (same path as submit); it does not re-fetch a server-stored PNG. iOS Safari / real-device preview refresh is not automated.

### 11.2 Canvas JSON schema (`schema_version` 1) — storage B1

Logical working canvas: **800×800** units (provisional; not garment or print size). Garment template/color remain `Design` model fields (not inside Fabric objects).

```json
{
  "schema_version": 1,
  "width": 800,
  "height": 800,
  "canvas": { "...": "FRONT Fabric.js canvas.toObject() output" },
  "views": { "back": { "...": "BACK Fabric canvas JSON" } }
}
```

- **`canvas` is always the FRONT view.** Older saves without `views` load as front-only; the client always writes `views.back` (empty Fabric canvas when unused).
- **`getCanvasJSON` / `preparePersistPayload` / commit snapshots** use the **full** envelope (both views).
- **`getActiveCanvasJSON`** returns only the active view’s canvas (for AI context).
- **`loadCanvasJSON`** replaces all views (front → live Fabric, `views.back` → `viewStore`, `activeView = "front"`).
- **`previewCanvasJSON` / `applyCanvasJSON`** replace **only** the active live canvas; AI candidates with a `views` key are rejected.
- **`setActiveView`**: snapshots the live canvas into the inactive store, loads the target via `loadFabricPayload` with commits suppressed (0 commits; does not call `notifyCommitted`). Blocked while AI candidates are pending (`VIEW_SWITCH_DURING_AI_PREVIEW = blocked`).
- **Stale-client guard (server):** if `schema_version == 1` and the POST omits `views` while the stored design has a `views` key with objects, stored views are kept. Explicit `views` (even empty) overwrites. Non-v1 payloads stay opaque.

**Shared safety rules** (`scanCanvasPayload` ↔ `canvas_safety.py`; must stay identical): depth ≤ 20; typeKey allowlist `rect|ellipse|circle|line|polygon|path|text|itext|textbox|image` (Groups/unknown rejected); `src|source|url|href|xlink:href` strings must be `data:image/(png|jpeg|webp);base64,`; pattern fills with `source` rejected; `backgroundImage` / `overlayImage` rejected; `views` keys only `back` (`views.front` rejected); `text` may contain `https://`.

**Image pipeline:** input ≤ `IMAGE_INPUT_LIMIT_BYTES` (8 MiB); decode via `createImageBitmap` / Image; reject `IMAGE_MAX_PIXELS`; longest edge ≤ `IMAGE_MAX_EDGE` (**2000** px); downscale/re-encode toward `IMAGE_TARGET_BYTES` (300 KB) using `IMAGE_EDGE_STEPS` / `IMAGE_QUALITY_STEPS`; keep original data URL when already small; 80% insert budget and 2 MiB hard cap measured on the **whole envelope** via `measureEnvelopeBytes`.

**Commits:** `commitEdit(label, applyFn)` → one `notifyCommitted` per successful op; `runSilent` suppresses; first committed edit after AI preview discards the sibling candidate. `SERIALIZE_PROPS`: `selectable`, `evented`, `blytzId`, `blytzName`, `blytzCurve`, `blytzLocked`. Fabric `visible` is a built-in (always serialized). Fabric object type `i-text` → `typeKey` strips non-letters → `itext` for comparisons.

**Layer management (Stage D):** Layers panel supports rename / duplicate / hide-show / lock-unlock. Rename changes `blytzName` only (trim; reject empty; max `PROP_LIMITS.layerNameMax` = 60); `blytzId` unchanged. Duplicate uses `duplicateActive` → new `blytzId`, name via `duplicateLayerName` (`… copy`), copies formatting/`blytzCurve`/image src; clone is forced **visible + unlocked** even if the source was hidden/locked. Hide/show toggles Fabric `visible` (stays in JSON + layer list; canvas hit-testing skips hidden; hiding the active object discards selection). Lock sets `blytzLocked` and applies `selectable`/`evented`/movement/scale/rotate locks + `hasControls: false`; `loadFabricPayload` re-applies lock interaction so reload cannot re-enable locked objects. **Layer-panel management selection** uses `selectObjectById` / `setActiveObject` and works for locked or hidden objects (rename, unlock, show, duplicate); **canvas pointer selection** does not hit locked (`evented`/`selectable` false) or hidden objects. All layer ops go through `commitEdit` (same undo stack). Curve Text preview still uses `runSilent` until Apply; Properties `syncFromSelection` clears the panel body and discards curve preview when selection clears or the panel is hidden so stale Apply/Cancel cannot mutate a prior object.

**Garment layers:** Assets in `static/garments/` (`tee`, `polo`, `hoodie`, `jersey` × front/back, 800×800). Client fetches SVG text (in-memory cache + `?v=` bust), splits into two inline SVGs sharing full `<defs>`: **under** (`#editor-garment-layer` = ground+base, first child of `#editor-canvas-wrap`) and **over** (`#editor-garment-overlay` = details+shade, last child, `pointer-events: none`). The SVG `art` group is omitted (Fabric is the art layer). OVER ids are rewritten (`…-` → `…-o-`) so defs do not collide. CSS variables `--garment`, `--trim` (`contrastColor(garment)`), `--string` (`#e9e5da` for hoodie drawcords) are set on the wrap and both SVGs for live display. Print areas come from `garments.json` (dashed guides on the over layer only; never drawn into export markups). Optional `data-blytz-lite-garment="1"` strips grain/weave rects from the over layer. Fabric background stays transparent. Template allow-list (`tee|polo|hoodie|jersey`) is identical in `garment_choices.py` and `editor_garments.js`; load-time aliases (e.g. `t-shirt`→`tee`) plus data migration `0005_normalize_garment_templates`; unknown keys rejected on save. Contrast defaults: new text/shapes/graphics/lines use `contrastColor(garment)` at insert time only.

**Print-area overflow warning (Stage 1):** `BlytzGarments.getPrintAreas(garmentId, viewId)` returns catalog rectangles only (no invented sizes). `BlytzCanvas` compares each object's transformed AABB (`getBoundingRect()` / Fabric 6 `getCoords()`) against those areas; artwork that is not fully inside at least one area shows a **DOM-only** `#editor-print-overflow-warning` banner. The banner is an **absolutely positioned overlay inside `#editor-canvas-wrap`** (not a host flex sibling) so show/hide cannot reflow artboard sizing, ResizeObserver, Fabric `cssOnly` dimensions, or garment SVGs. The warning never moves/resizes/clamps artwork, is not a Fabric object, and is omitted from canvas JSON and PNG export (guides already stripped via `hidePrintAreas` / export markups). Rechecks are rAF-throttled on move/scale/rotate and also run after commits, view switches, garment/color changes, and loads. Missing print-area definitions disable the overflow banner (`defined: false`) rather than inventing guides. Geometry twin: `apps/designs/print_area_check.py`.

**Align / center / flip (Stage 2):** Properties panel controls call `BlytzCanvas.alignActive(direction, mode)`, `centerOnCanvas(axis)`, and `flipActive(axis)` through `commitEdit` (one undo step each; Front/Back unchanged). Single-object align uses the logical 800×800 canvas; multi-object align uses the selection AABB (`mode: "selection"`). Canvas centering moves the whole selection by one shared delta (labels say “Center on canvas”). Flip toggles Fabric `flipX` / `flipY` without minting ids or renaming layers. ActiveSelection is discarded to absolute coords before transforms, then restored — avoids selection-local mistakes. Print overflow rechecks via existing after-commit hooks. Geometry twin: `apps/designs/align_flip.py`.

**Composition tools (Stage F):** Extends Stage 2 align/center/flip — no Fabric groups, no schema changes, no persistent grouping. **Distribute** (`distributeActive("horizontal"|"vertical")`) requires ≥3 selected objects; uses **transformed AABBs** (`getBoundingRect` / twin `distribute_rects`), not raw `left`/`top`. Rule: sort by AABB left (H) or top (V) with stable index ties; keep first and last fixed; place intermediates so **edge-to-edge gaps are equal** `(span − sum(sizes)) / (n − 1)`. Unequal sizes are honored via AABB extents (not center-to-center spacing). Negative gaps (overlap) still even out. **Multi-center** reuses `centerOnCanvas` with one shared delta so relative arrangement is preserved. **Locked policy (reject-all):** if any selected member has `blytzLocked`, align / distribute / center / flip reject the whole op with feedback and **no history entry** — never silently skip or move locked objects. UI disables composition buttons when locked or when distribute count < 3 (no fake-enabled). **Multi-duplicate** extends `duplicateActive` to clone the whole ActiveSelection in one `commitEdit` (`duplicate-selection`), minting a fresh `blytzId` + `duplicateLayerName` per clone (clones forced visible+unlocked). **Delete** selection remains one undoable `deleteSelection`. **Clear selection** (`clearSelection` / Escape when the props sheet is not open) discards ActiveSelection without `commitEdit` or dirtying the design. Geometry twin additions live in `apps/designs/align_flip.py` (`distribute_rects`, `composition_rejects_locked`).

**Auto layout (UC-06):** One-click **deterministic** rearrange of the **active view only** (Front or Back currently shown) — no AI/ML, no learning, no silhouette path clipping. Entry points: toolbar **Auto layout** (`data-editor-action="auto-layout"`) and Properties **Auto layout**. Calls `BlytzCanvas.autoLayoutActive` → one `commitEdit("auto-layout")` (single Undo step). Slots are derived from the garment **primary print panel** (`id` `front`|`back` from catalog; else largest area): **center**, **left-chest**, **right-chest**, **wordmark** / text-under (fractions of panel rect). **Ordering:** canvas bottom→top index (stable). **Rules:** (1) first image → center; (2) second → left-chest; (3) third → right-chest; images beyond 3 **left unmoved** + feedback; (4) text(s) stacked below the primary (first) image with a fixed gap; (5) text-only → first/largest-order text as centered wordmark, remaining stacked below; (6) after placement, uniform scale-down + clamp AABB inside the primary panel; (7) **skip** hidden (`visible===false`) and locked (`blytzLocked`) — layout the rest with brief feedback (unlike Stage F reject-all); (8) empty / nothing movable → no-op + feedback. Print-overflow warning / `canvas_safety` unchanged (layout aims to stay inside the primary panel). Geometry twin: `apps/designs/auto_layout.py`.

**Undo/Redo chrome:** Top-bar `.editor-undo-redo` is `display: inline-flex` on desktop (previously hidden except coarse/phone). Buttons use `data-editor-undo` / `data-editor-redo` with **SVG icon + text label**; `syncHistoryUi` sets `disabled` from `canUndo` / `canRedo`. Header action cluster (`.editor-top-actions`) uses a clearer horizontal gap so Undo, Redo, Design info, Preview, Save, Submit do not feel cramped. Clicks and Ctrl/Cmd+Z / Shift+Z / Y call the same `BlytzEditor.undo` / `redo` (no parallel history).

**Text formatting:** Properties registry for `itext|text|textbox` adds Bold (`fontWeight`), text align (`textAlign` left/center/right), letter spacing (`charSpacing`, Fabric 1/1000 em), and line spacing (`lineHeight` multiplier). Text-only; ActiveSelection and non-text types are rejected. Commits use `commitEdit`. Helper twin: `apps/designs/text_format.py`.

**Image editing (Stage E):** Single selected `image` only (not text/shapes/ActiveSelection). Properties expose effective **width/height** via Fabric `scaleX`/`scaleY` (canvas coords; `sizeMin`/`sizeMax` = 8–1600 so intentional overflow of 800×800 is allowed); blank/non-finite/zero/negative rejected. **Aspect ratio** locked by default (`keepProportions`); unlock for independent dims. **Rotation** degrees with center preserved + reset-to-0° (`resetActiveRotation`); print-overflow rechecks via existing after-commit hooks. **Opacity** 0–100% range + numeric; live preview via `beginLive`/`endLive` → one `commitEdit` at pointer-up. **Placement:** Center (`centerActiveImage` → `centerOnCanvas("both")`), Fit within canvas (`fitActiveWithinCanvas` — uniform scale, preserve aspect, then center; never stretch-to-fill), Reset ° (rotation only). Locked images (`blytzLocked`) show a readonly notice and disable controls; APIs no-op with feedback. Does not switch Front/Back, replace `src`, or mint/rename ids. Commits reuse `commitEdit` / live end-commit; no parallel history. Helper twin: `apps/designs/image_edit.py`.

**Image crop (deferred):** Not shipped in Stage E. Fabric 6.6.1 `cropX`/`cropY` mutate native image `width`/`height`, which conflicts with the scale-based Properties dims model and would require a separate cancel/apply session plus save/reload validation. A `clipPath` Rect would pass the existing nested allowlist scan but is **visual clip only** — not a durable crop of source pixels — and must not be claimed as crop. Smallest future approach: dedicated crop session (like curve preview) that applies `cropX`/`cropY` + native size in one `commitEdit`, keeps `src`/`blytzId`/`blytzName`, and teaches Properties dims to treat crop-native size as the base for scaling.

**Preview PNG export (`includeGarment: true`):** `BlytzGarments.getExportLayerMarkups` loads the target view’s SVG (cache/fetch), bakes exact strings `var(--trim, var(--garment, #f2f2ef))` → trim hex, then `var(--garment, #f2f2ef)` → garment hex, then `var(--string, #e9e5da)` → string hex, asserts no `var(` remains, lowers grain opacity for file size, splits under/over, and composites with Fabric artwork (active view via live `toDataURL`; other view via offscreen `StaticCanvas`). Result must pass `services/preview_images.py` (real PNG, ≤5 MB, max edge 2400). Failures block submit (no order).

**UI breakpoints:** bottom toolbar + Edit pill ≤1023px; Properties sheet exclusive with tool panels when `!min-width:1280` (CSS `not all and (min-width: 1280px)`); coexist ≥1280px. Front/Back: always-visible overlay toggle group (`#editor-view-toggle`) plus toolbar toggle. Phone Text tool opens a Text sheet (no Fabric `enterEditing` on coarse/narrow viewports). Landscape coarse tablets use docked panels via `editor_chrome.js` (`data-editor-layout`).

**Client persist guards:**

- `loadCanvasJSON()` readiness via `getLoadState()` / `whenReady()` / `canPersist()`.
- Save/Submit use `preparePersistPayload()` (2 MiB UTF-8 whole-envelope cap).
- Unsafe saved loads use the failed-load pathway (persist blocked; stored data not overwritten).
- Additive BlytzEditor methods: `getActiveView`, `setActiveView`, `onViewChange`, `getActiveCanvasJSON`, `getGarmentState`, `setGarmentState`, `onGarmentChange`, `undo`, `redo`, `canUndo`, `canRedo`.

**Deployment note:** stale cached scripts caused false failures earlier — prefer hashed static filenames in production. B1 stale clients that omit `views` are additionally covered by the server guard (hashed filenames not implemented in this stage).

**Known limitations:** front/back only (no sleeve views); real-device keyboard/pinch still worth a manual pass (`qa/manual_device_checklist.md`); client deterrents do not stop screenshots; safety rules are duplicated in JS and Python; preview PNG compositing / SVG-as-`<img>` CSS-var baking is verified in desktop browsers via `qa/garment_checks.js` — **iOS Safari and real phones are not automated** (manual check recommended for submit mock-ups and grain file size).

### 11.3 Legacy compatibility

| Incoming data | Client load | Server save/submit |
| --- | --- | --- |
| Blytz `{schema_version:1, canvas:{…}}` | Load Fabric payload | Accept + safety scan |
| Empty legacy stub / seed: `{version:1, objects:[]}` (optional `stub`, `demo`, …) | Empty canvas (ready to edit/save) | Accept |
| Raw Fabric canvas JSON (`version` string + `objects`) | Wrap into schema v1 and load | Accept (opaque; client rewrites to v1 on next save) |
| Unknown `schema_version` (≠ 1) | **Not loaded** — persist blocked; original preserved | Opaque round-trip (forward-compat) |
| Non-empty pre-Fabric stub objects (e.g. `{version:1, objects:[{type:"text"}]}`) | **Not loaded** — persist blocked | **Rejected** (aligned with client) |
| Missing / malformed JSON | Empty workspace + persist blocked when data was expected to load | Reject invalid JSON |

**Current state:** Fabric-backed editor; save/submit accept supported formats only. Unsupported legacy stubs are rejected rather than stored as data the editor cannot reopen.

---

## 12. Services layer

```
services/
  __init__.py
  proof_images.py    # payment proof verify / shrink / strip metadata
  preview_images.py  # submit mock-up PNG validate (Pillow)
  ai_design.py       # Stage O Gemini two-candidate design suggestions
```

**Wrappers**

1. **proof_images** — live; used by submit + order-page uploads  
2. **preview_images** — live; validates front/back mock-up PNGs at design submit  
3. **ai_design** — Stage O; `suggest_design_candidates()` calls Gemini REST (stdlib `urllib`); apps never talk to Gemini directly; key from settings only  
4. **Email** — transactional mail beyond console (django-anymail + HTTPS provider) (planned)  

**Client (not services/):** Stage R.2 background removal uses `@imgly/background-removal` in the browser (`static/js/remove_bg_client.js`).

### 12.1 Stage O / O.1 — AI-assisted design suggestions

Additive customer feature on top of the Stage 2 chat UX (`#ai-assistant` + `ai_chat.js`).

| Piece | Behavior |
| --- | --- |
| Endpoint | `POST /app/designs/<id>/ai/suggest/` (`design_ai_suggest`) — `@customer_required`, owner-only, JSON body |
| Request | `{ message, canvas_json, active_side, garment_template?, garment_color? }` — **Design row** is source of truth for garment |
| Response | `{ ok, message, suggestions: [{ id, label, description, canvasJSON, otherSideCanvasJSON? }, ×2], dual_side, print_areas }` |
| Print areas | Catalog `static/garments/garments.json` (+ embedded `editor_garments.js` + `generate_garments.py` AREAS): **primary** panels use id `front`/`back` = **full visible flat front/back of the mockup including sleeve areas as drawn on the 2D SVG** (body + sleeves). Still **not** 3D wrap and **not** separate physical sleeve print jobs. Jersey back may also list `name`/`number` sub-guides nested inside the large back panel; **AI bounds use primary only** |
| Prompt | Backend injects garment, color, side(s), primary print rects, current canvas; apparel-only; prefer panel fill (slight overflow OK); printable = flat mockup face incl. sleeves |
| Validation | Schema v1 + 2 MiB + `canvas_safety` + **no `views` key** + soft AI print bounds (primary panel **+ `AI_PRINT_OVERFLOW_MARGIN_PX`**, default **40px** after Stage O.1.2 full panels — was 60 when panels were torso-only — clamped to 800×800; reject fully off-canvas); optional `otherSideCanvasJSON` when dual-side; far overflow → retry up to 2× then HTTP 400. **Editor dashed guides + overflow warning stay strict** (no margin) for manual correction |
| Images | Prior canvas `image` objects soft-merged into candidates unless the user asks to clear/replace images |
| Dual-side | On for `jersey` or explicit “front and back” / “both sides” prompts; `otherSideCanvasJSON` applied to inactive view on first commit via `setStoredViewPayload` |
| Rate limit | 5 **successful** calls per user per hour; only final OK consumes quota (retries do not) |
| Persistence | Never writes `Design.canvas_json` and never creates Orders (prompt/AI audit fields not stored yet) |
| Logging | Metadata only (user, design id, success/failure, token counts, dual_side) — not prompts or canvas JSON |
| Client | `previewCanvasJSON` for tentative loads; first real `commitEdit` keeps active candidate (+ other side if present) and discards the other |
| Offline | If `GEMINI_API_KEY` is empty, editor shows AI unavailable and `ai_chat.js` falls back to the local Stage 2 mock |

Rule: apps import from `services.*`, never vendor SDKs directly.

**Still deferred:** reference-image → AI, area-specific click-to-place (%), 3D contours, storing original prompts / AI JSON at submit.

### 12.2 Stage R.2 — Background removal (client `@imgly/background-removal`)

Replaces Stage R.1 remove.bg (server API + credits). No `REMOVE_BG_*` settings and no remove-bg HTTP endpoint.

| Piece | Behavior |
| --- | --- |
| Library | `@imgly/background-removal@1.7.0` loaded via dynamic `import()` from esm.sh (`static/js/remove_bg_client.js`); exposes `window.BlytzRemoveBg` |
| Assets | ONNX/WASM fetched on **first use** (browser-cached); progress feedback “Loading model…” / “Removing…” |
| Client UX | Properties → Image placement → **Remove BG** on a selected unlocked image; PNG **data URL** → `replaceActiveImageSrc` (one undo step) |
| Safety | Output must stay `data:image/…;base64` (canvas_safety); no `blob:` persistence |
| License | AGPL-3.0 for the IMG.LY package — see `static/vendor/imgly/LICENSE.md` (capstone: document; commercial: review) |
| Offline / fail | Network needed for first model load; failures show tool feedback (no server fallback) |

**Still deferred:** auto-remove on every upload, vendoring models under `static/` (`publicPath`), local rembg server fallback.

---

## 13. Configuration & environment

### 13.1 Settings module highlights (`config/settings.py`)

| Area | Behavior |
| --- | --- |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | From env |
| Proxy TLS | `USE_SECURE_PROXY_SSL_HEADER` or `SECURE_PROXY_SSL_HEADER=header,value` |
| Database | `env.db("DATABASE_URL", default=sqlite:///…/db.sqlite3)` |
| `AUTH_USER_MODEL` | `accounts.User` |
| Static | `STATICFILES_DIRS=static/`; `STATIC_ROOT=staticfiles/`; WhiteNoise |
| Media | `MEDIA_ROOT=media/`; served in DEBUG via urls |
| Tailwind | `TAILWIND_CLI_SRC_CSS`, `TAILWIND_CLI_DIST_CSS` |
| Business | `MESSENGER_PAGE_USERNAME`, `PAYMENT_WINDOW_MINUTES`, `PROOF_MAX_UPLOAD_MB` |
| Stage O AI | `GEMINI_API_KEY`, `GEMINI_MODEL`, `AI_SUGGEST_RATE_LIMIT_PER_HOUR`, `AI_SUGGEST_RATE_LIMIT_WINDOW_SECONDS`, `AI_PRINT_OVERFLOW_MARGIN_PX` (default 40) |
| Email | Console default; `ANYMAIL` dict reserved |
| Sites | `SITE_ID=1` for allauth |

### 13.2 Environment variables (`.env.example`)

| Variable | Default / example | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | change-me… | Django secret |
| `DEBUG` | `True` | Dev mode |
| `ALLOWED_HOSTS` | localhost,127.0.0.1 | Hosts |
| `CSRF_TRUSTED_ORIGINS` | empty | HTTPS origins (Railway) |
| `USE_SECURE_PROXY_SSL_HEADER` | optional | Railway TLS |
| `SECURE_PROXY_SSL_HEADER` | optional | `HTTP_X_FORWARDED_PROTO,https` |
| `DATABASE_URL` | unset → SQLite | MySQL later |
| `MESSENGER_PAGE_USERNAME` | your_page_username | m.me deep-link |
| `PAYMENT_WINDOW_MINUTES` | `10` | Submit deadline |
| `PROOF_MAX_UPLOAD_MB` | `15` | Payment proof max upload size |
| `GEMINI_API_KEY` | empty | Stage O Gemini key (empty disables live AI) |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model id (alt: `gemini-3.1-flash-lite`; 2.5 → 404 for new keys) |
| `AI_SUGGEST_RATE_LIMIT_PER_HOUR` | `5` | Successful AI suggests per user per window |
| `AI_SUGGEST_RATE_LIMIT_WINDOW_SECONDS` | `3600` | Rate-limit window |
| `AI_PRINT_OVERFLOW_MARGIN_PX` | `40` | Soft AI overflow past primary print panel (UI warning stays strict) |
| `EMAIL_BACKEND` | console | Swap to anymail later |
| `DEFAULT_FROM_EMAIL` | noreply@blytz.local | From address |

---

## 14. Static assets, media & Tailwind

```
src/styles/main.css  ──tailwind build/watch──►  static/css/tailwind.css
static/js/*                                      browser
static/img/*
media/payment_channels/                          QR uploads
media/payment_proofs/                            payment proofs
media/design_previews/ · order_previews/ · final_designs/
static/vendor/chartjs/                           Chart.js 4.4.6 (staff charts)
static/vendor/fabric/                            Fabric.js (editor)
static/garments/                                 Apparel SVGs + garments.json
```

**Dev commands**

```bash
python manage.py tailwind build
python manage.py tailwind watch
python manage.py tailwind runserver   # preferred: Tailwind + Django together
```

**Production:** `collectstatic` → WhiteNoise `CompressedManifestStaticFilesStorage` when not DEBUG.

---

## 15. Deployment

### 15.1 Process model

```
Procfile:
  web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

### 15.2 Railway / production checklist

1. `DEBUG=False`, strong `SECRET_KEY`
2. `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` (e.g. `https://your-app.up.railway.app`)
3. `USE_SECURE_PROXY_SSL_HEADER=True` (or explicit `SECURE_PROXY_SSL_HEADER`)
4. Optional `DATABASE_URL=mysql://…` (PyMySQL shim already in `config/__init__.py`)
5. Run migrations + `collectstatic` in build
6. Email: keep console locally; later anymail HTTPS provider + `ANYMAIL` config
7. Do not commit `.env`, `db.sqlite3`, `media/`, `staticfiles/`

### 15.3 Local setup (summary)

```bash
python -m venv .venv
# activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py tailwind build
python manage.py tailwind runserver
```

---

## 16. Seed data & demo accounts

Command: `python manage.py seed_demo` (idempotent, atomic).

| Email | Role | Notes |
| --- | --- | --- |
| `admin@blytz.demo` | Admin | Superuser |
| `staff.accounting@blytz.demo` | Staff | `can_edit_accounting=True` |
| `staff@blytz.demo` | Staff | Accounting view-only |
| `customer1@blytz.demo` … `customer5@blytz.demo` | Customer | Designs + orders |

**Password (all):** `demo-pass-123`

**Seed contents**

- 3 active payment channels (GCash, Maya, Bank) with generated QR placeholders
- 12 designs (10 submitted with orders/leads/payments; 2 remain drafts)
- Orders across all job statuses; mixed fully paid / outstanding / unset agreed total
- Front/back placeholder preview PNGs on seeded orders
- `Order.created_at`, payment `created_at`, and `OrderPhaseChange` timestamps spread over the last 60 days (charts look realistic)
- Payments mix **accepted**, **pending**, and **rejected** (some orders show “Payment awaiting review”)
- Leads covering all stages
- Activity logs for created/submitted/confirmed

---

## 17. Testing

Run: `python manage.py test` or `python manage.py test apps.designs`.

| Test module | Focus |
| --- | --- |
| `apps.accounts.tests.test_access` | Role guards / redirects |
| `apps.accounts.tests.test_admin_pages` | Admin user/channel pages |
| `apps.designs.tests.test_ownership` | Owner isolation |
| `apps.orders.tests.test_order_list` | Stage J customer submission history / isolation / pagination |
| `apps.designs.tests.test_submit` | Submit transaction / window / Stage I duplicate JSON + snapshot |
| `apps.designs.tests.test_submit_workflow` | Stage I submit lock / fingerprint source + editor markup |
| `apps.designs.tests.test_save_state` | Stage G save-state / readiness source + save rejection |
| `apps.designs.tests.test_design_preview` | Stage H/H.1 preview markup / save-refresh contracts + ownership |
| `apps.designs.tests.test_canvas_schema` | Schema round-trip + SOURCE-STRING |
| `apps.designs.tests.test_ai_suggest` | Stage O AI suggest auth / rate limit / two candidates / validation (Gemini mocked) |
| `apps.designs.tests.test_canvas_safety` | Shared safety rules (BEHAVIOR) |
| `apps.designs.tests.test_garment_views` | Garment fields + B1 views (BEHAVIOR/SOURCE-STRING) |
| `apps.orders.tests.test_models` | Order ID, payment aggregates, phases |
| `apps.orders.tests.test_payment_review` | Accepted-only totals, gate, review perms, uploads, race constraint |
| `apps.orders.tests.test_proof_processing` | 15/16 MB limits, shrink/orientation/metadata, corrupt/PDF |
| `apps.orders.tests.test_staff_order_detail` | Staff fields/mock-ups, artwork download perms, phase history |
| `apps.orders.tests.test_final_design` | Final design upload/replace/version, customer approve, stale version, perms, manual Production move |
| `apps.accounting.tests.test_staff` | View vs edit accounting; manual adj. auto-accepted |
| `apps.accounting.tests.test_export` | Staff CSV export authz, distinct job/payment status columns, filters, read-only |
| `apps.core.tests.test_production_settings` | `DEBUG=False` rejects placeholder `SECRET_KEY` |
| `apps.accounting.tests.test_charts` | Accounting charts perms, accepted-only aggregates, empty states |
| `apps.accounts.tests.test_staff_charts` | Overview charts perms, phase/pending aggregates, empty states, jobs pending_review filter |
| `apps.core.tests.test_landing_nav` | Landing redirects / nav / staff role badge |
| `apps.core.tests.test_template_leaks` | Template leakage checks |
| `apps.core.tests.test_responsive_chrome` | Responsive CSS/JS contracts, pipeline modes, editor phone chrome, payment sheet |
| `apps.designs.tests.test_rename` | Draft rename, empty → Untitled, post-submit reject, ownership |

**Browser QA:** paste scripts from `qa/` (`gate.js`, `regression_commits.js`, `garment_checks.js`) into DevTools on the editor with cache disabled. `qa/manual_device_checklist.md` covers real-phone items. Playwright is **not** approved/installed for this stage.

---

## 18. Error handling & security notes

| Topic | Behavior |
| --- | --- |
| 403 / 404 / 500 | Django defaults (`handler403/404/500` in `config/urls.py`); custom templates `403.html`, `404.html`, `500.html` |
| CSRF | Middleware + editor JS reads `csrftoken` cookie |
| Ownership | Customer queries always filter by owner/customer |
| Phase advance | Server ignores client-supplied next status; only `PHASE_FLOW` next; accepted payment required before Pending Edit |
| Final design upload | Staff/admin only; Pending Edit only; replace deletes prior file and bumps version |
| Final design approve | Order owner only; Pending Edit only; posted version must match `final_design_version` |
| Payment review | Staff/admin only; pending → accepted/rejected; customers 403 |
| Additional proofs | One pending max; blocked when fully paid; race-safe lock + unique constraint |
| Admin self-harm guards | No self-demote / self-deactivate; ≥1 active admin |
| Media in prod | Not auto-served by Django when `DEBUG=False` — needs object storage or proxy config later |
| Secrets | `.env` gitignored; never commit credentials |
| Production guard | `DEBUG=False` rejects known placeholder `SECRET_KEY` values; enables secure cookies / SSL redirect / nosniff / referrer policy (env-overridable) |
| Staff CSV export | `@staff_required` read-only; customers 403; does not mutate Order/Payment/Design |

**Business policy reflected in UI copy:** strictly no refunds; P2P money never settles inside Blytz — only claimed amounts and proofs are stored.

### 18.1 Capstone security posture (Stage N audit)

**Verified in code / automated tests (actual controls):**

| Area | Evidence |
| --- | --- |
| Role gates | `@customer_required` / `@staff_required` / `@admin_required` → 403 (`apps.accounts.tests.test_access`, accounting/staff tests) |
| Ownership / IDOR | Design/order queries filter `owner` / `customer`; approve re-checks `customer_id` under `select_for_update` (`test_ownership`, `test_final_design`, submit tests) |
| CSRF | `CsrfViewMiddleware` in middleware stack; forms use `{% csrf_token %}` |
| Canvas limits | `MAX_CANVAS_JSON_BYTES` 2 MiB + `validate_v1_envelope` on save/submit |
| Uploads | Proof/final-design allow-lists + size caps (`apps.orders.proof`); preview PNG validation on submit |
| Duplicate order | `unique_order_per_design` + submit transaction / concurrency tests (SQLite) |
| Payment vs job status | Distinct fields/labels; export CSV keeps separate columns |

**Theoretical / untested in this pass (not claimed production-ready):**

| Item | Notes |
| --- | --- |
| Real MySQL/PostgreSQL concurrency | Submit races tested on SQLite only |
| Production host / HTTPS termination | Railway checklist documented; no live deploy verified here |
| Real payment provider | P2P proof upload only — no gateway |
| Media CDN / private media ACL | Filesystem `media/`; public URL exposure depends on host config |
| `ACCOUNT_LOGOUT_ON_GET=True` | Logout via GET can be CSRF-triggered to log users out (session theft not implied); left as-is to preserve nav link UX |
| iOS Safari / real-device editor | Manual checklist exists; not automated |

### 18.2 Capstone demo flow

1. `python manage.py migrate` → `python manage.py seed_demo` → `python manage.py runserver` (or `tailwind runserver`).
2. **Customer** (`customer1@blytz.demo` / `demo-pass-123`): Designs → Start new design → edit Front/Back → Save → Preview → Submit with channel + amount + proof → Orders list → order detail (job phase ≠ payment status).
3. **Staff** (`staff@blytz.demo` or `staff.accounting@blytz.demo` / `demo-pass-123`): Jobs pipeline → open order → inspect mock-ups / design snapshot → accept/reject payment → advance phase (accepted payment required before Pending Edit).
4. **Accounting / reports:** `/staff/accounting/` → optional filters → **Export CSV** (`/staff/accounting/export.csv`). Admin (`admin@blytz.demo`) can do the same plus users/channels.
5. Password for all seeded demo users: `demo-pass-123`.

---

## 19. Planned / not-yet-implemented

| Item | Status |
| --- | --- |
| Fabric.js (or full) canvas editor | Stage 1: Fabric 6.6.1 + Blytz schema v1 (basic tools) |
| AI chat (mocked) / two-candidate preview + commit-on-edit | Stage 2 base UX in `ai_chat.js` |
| Stage O — Gemini two-candidate suggest | Shipped: `services/ai_design.py` + `design_ai_suggest` + live/mock `ai_chat.js` |
| Stage O.1 — print panels, zone prompts, bounds, image merge, jersey dual-side | Shipped (see §12.1) |
| Stage O.1.1 — soft AI print overflow margin | Shipped (`AI_PRINT_OVERFLOW_MARGIN_PX`; UI warning still strict) |
| Stage O.1.2 — full flat front/back panels (body + sleeves on mockup) | Shipped (catalog sync; AI soft margin default 40; still not 3D) |
| Stage R.1 — remove.bg server path | Removed in R.2 |
| Stage R.2 — client `@imgly/background-removal` | Shipped (see §12.2); no API credits |
| UC-06 — rule-based Auto layout + header Undo/Redo chrome | Shipped (deterministic slots from primary print panel; see §11.2) |
| Area-specific prompting refinements | Later (optional) |
| HTTPS transactional email (anymail) | Commented optional dep + `ANYMAIL` stub |
| MySQL in production | Supported via `DATABASE_URL`; SQLite is default |
| Design `preview_image` (design draft thumb) | Optional field; order front/back mock-ups persisted at submit |
| Activity kinds `design_revised` / `design_approved` | Emitted on final-design replace (v>1) and customer approval |
| Dedicated media CDN / S3 | Filesystem `media/` today |

---

## 20. Quick reference matrices

### 20.1 App → models → primary URLs

| App | Models | Primary surfaces |
| --- | --- | --- |
| accounts | User | Profile, staff home, users admin |
| core | — | Landing, component gallery |
| designs | Design, ActivityLog | Dashboard, list, editor, save, submit |
| orders | Order, OrderPhaseChange, Payment, PaymentChannel | Customer orders, jobs, channels |
| accounting | — | Accounting list/detail |
| sales | Lead | Sales pipeline, lead detail |

### 20.2 Middleware order

1. `SecurityMiddleware`  
2. `WhiteNoiseMiddleware`  
3. `SessionMiddleware`  
4. `CommonMiddleware`  
5. `CsrfViewMiddleware`  
6. `AuthenticationMiddleware`  
7. `MessageMiddleware`  
8. `XFrameOptionsMiddleware`  
9. `allauth.account.middleware.AccountMiddleware`

### 20.3 Order status ↔ UI step index

| Status | Stepper index |
| --- | --- |
| job_request | 1 |
| pending_edit | 2 |
| production | 3 |
| completed | 4 |

### 20.4 Context processor keys (all templates)

- `MESSENGER_PAGE_USERNAME`
- `messenger_url`
- `PAYMENT_WINDOW_MINUTES`
- `PROOF_MAX_UPLOAD_MB`
- `DEBUG`

---

## Appendix A — INSTALLED_APPS

```
django.contrib.admin
django.contrib.auth
django.contrib.contenttypes
django.contrib.sessions
django.contrib.messages
django.contrib.staticfiles
django.contrib.sites
allauth
allauth.account
django_tailwind_cli
apps.accounts
apps.core
apps.designs
apps.orders
apps.accounting
apps.sales
```

## Appendix B — Document maintenance

When changing architecture, update this file alongside:

- `docs/PROJECT_BRIEF.md` — product goals, brand tokens, model summary  
- `README.md` — setup, routes, seed table  
- `.cursor/rules/blytz.mdc` — contributor conventions  

*Generated from the repository as of the documentation write date. Reflects implemented code, not aspirational backlog except §19.*
