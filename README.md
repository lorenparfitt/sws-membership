# SWS Membership

Membership, pass and waiver platform for the Squamish Windsports Society.
A Django backend on Postgres, a JSON API through Django Ninja, and a React
frontend. Payments are taken
through Nuvei; member numbers are the Code128 barcodes printed on member
cards.

## Layout

- `backend/` Django project `sws_membership`: one app per area, migrations, tests.
- `frontend/` React application built with Vite.
- `docker-compose.yml` local Postgres.
- `dodo.py` every top-level action. Developers and CI run the same tasks.
- `docs/dependencies.md` what the platform is built on and why each piece is there.

## Running locally

The Nix flake provides every tool; enter it with `nix develop` (or direnv).
Run tasks from the repo root:

```
uv run doit list        # all tasks
uv run doit db_up       # start Postgres in Docker
uv run doit migrate     # apply migrations
uv run doit seed        # made-up members and the sample catalog
uv run doit api         # API on http://localhost:8000
uv run doit web_install # once
uv run doit web         # frontend on the Vite dev server, proxied to the API
uv run doit check       # lint and tests, the gate CI runs
uv run doit manage --args "create_member you@example.com First Last --password ..."
uv run doit manage --args "grant_role you@example.com admin"
```

Django's own admin site is at http://localhost:8000/django-admin/ for members
with the admin role.

Configuration is read from environment variables prefixed `SWS_`, or from
`backend/.env`. `SWS_DATABASE_URL` defaults to the compose database.
