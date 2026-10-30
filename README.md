# SWS Membership

Membership, pass and waiver platform for the Squamish Windsports Society.
A FastAPI backend on Postgres and a React frontend. Payments are taken
through Nuvei; member numbers are the Code128 barcodes printed on member
cards.

## Layout

- `backend/` Python package `sws_membership`, Alembic migrations, tests.
- `frontend/` React application built with Vite.
- `docker-compose.yml` local Postgres.
- `dodo.py` every top-level action. Developers and CI run the same tasks.

## Running locally

The Nix flake provides every tool; enter it with `nix develop` (or direnv).
Then:

```
uv run doit list        # all tasks
uv run doit db_up       # start Postgres in Docker
uv run doit migrate     # apply migrations
uv run doit api         # API on http://localhost:8000
uv run doit web_install # once
uv run doit web         # frontend on the Vite dev server, proxied to the API
uv run doit check       # lint and tests, the gate CI runs
```

Configuration is read from environment variables prefixed `SWS_`, or from
`backend/.env`. `SWS_DATABASE_URL` defaults to the compose database.
