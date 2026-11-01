# Dependencies

What the platform is built on, what each piece is for, and where its
version is pinned. Versions live in the manifests named here, not in
this file, so this stays true when they move.

## Platform and toolchain

| Layer | Choice | Pinned in |
|---|---|---|
| Python | 3.12, the system interpreter only; uv never downloads one | `backend/pyproject.toml`, `flake.nix` |
| Python packages | uv, with `uv.lock` at the repo root | `uv.lock` |
| Node | 24 | `flake.nix` |
| Database | PostgreSQL 16 | `docker-compose.yml` (server image), `flake.nix` (client) |
| Task runner | doit; every top-level action is a task in `dodo.py` | root `pyproject.toml` |
| Dev environment | a Nix flake that provides all of the above; Docker runs Postgres | `flake.nix`, `docker-compose.yml` |

## Backend (Python, `backend/pyproject.toml`)

| Package | Role |
|---|---|
| Django 5.2 | ORM, migrations, sessions, password hashing, the admin site, settings |
| Django Ninja | the JSON API: typed routes, Pydantic schemas, OpenAPI at `/api/docs` |
| Uvicorn | ASGI server for production; `runserver` in development |
| psycopg 3 | Postgres driver |
| httpx | outbound HTTP: Nuvei openOrder, Mailchimp Transactional |
| argon2-cffi | the Argon2 password hasher Django is configured to use |
| reportlab | member card PDFs, Code128 barcode and QR code |
| Pillow | photo normalisation: resize, re-encode, strip metadata |
| pytest, pytest-django, ruff | tests and lint, development only |

Configuration is read from `SWS_` environment variables or `backend/.env`
by `sws_membership/settings.py`, which derives Django's own settings from
them.

Tests run against a real Postgres database (`sws_membership_test`), created
and migrated by pytest-django, with each test rolled back.

## Frontend (TypeScript, `frontend/package.json`)

| Package | Role |
|---|---|
| React 19 | UI |
| react-router-dom 7 | routing |
| TypeScript | types; `tsc -b` runs before every build |
| Vite, with the React plugin | dev server with a proxy to the API, production build |

There are no other runtime packages. The signature pad, the barcode and
the card payment popup are hand written or rendered server side.

## External services

Each is behind a seam in the code and selected by a named profile in
settings, so development runs with no account anywhere.

| Service | Setting | Development stand-in |
|---|---|---|
| Nuvei Simply Connect (card payments) | `SWS_PAYMENT_PROCESSOR=nuvei` | `fake`: no form, an approve button that drives the real notification path |
| Mailchimp Transactional (receipts, sign-in links) | `SWS_MAIL_BACKEND=mailchimp` | `console`: messages are logged |
| Object storage (photos, signature images) | `SWS_STORAGE_DIRECTORY` | a local directory under `backend/var/storage` |
| Nuvei `checkout.js` | loaded in the browser from Nuvei's CDN at payment time | not loaded under the fake processor |

Card details never reach this platform: the processor's own form collects
them, and the webhook handler drops any card-shaped field before the
notification is stored.
