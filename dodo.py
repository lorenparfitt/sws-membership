"""Every top-level action, for developers and CI alike. Run `uv run doit list`."""

DOIT_CONFIG = {"default_tasks": ["check"], "verbosity": 2}

BACKEND = "backend"


def task_db_up():
    """Start the local Postgres container."""
    return {"actions": ["docker compose up -d postgres"]}


def task_db_down():
    """Stop the local Postgres container, keeping its data."""
    return {"actions": ["docker compose stop postgres"]}


def task_migrate():
    """Apply database migrations to the configured database."""
    return {"actions": [f"cd {BACKEND} && uv run alembic upgrade head"]}


def task_api():
    """Run the API with reload on the local machine."""
    return {
        "actions": [
            f"cd {BACKEND} && uv run uvicorn sws_membership.main:application --reload --port 8000"
        ]
    }


def task_test():
    """Run the backend test suite against the local Postgres."""
    return {"actions": [f"cd {BACKEND} && uv run pytest"], "task_dep": ["db_up"]}


def task_lint():
    """Lint and format-check the backend."""
    return {
        "actions": [
            f"cd {BACKEND} && uv run ruff check .",
            f"cd {BACKEND} && uv run ruff format --check .",
        ]
    }


def task_check():
    """Lint and test, the gate CI runs."""
    return {"actions": None, "task_dep": ["lint", "test"]}


FRONTEND = "frontend"


def task_web_install():
    """Install frontend dependencies."""
    return {"actions": [f"cd {FRONTEND} && npm install"]}


def task_web():
    """Run the frontend dev server, proxying API calls to the local backend."""
    return {"actions": [f"cd {FRONTEND} && npm run dev"]}


def task_web_build():
    """Type-check and build the frontend for production."""
    return {"actions": [f"cd {FRONTEND} && npm run build"]}


def task_manage():
    """Operator commands: uv run doit manage -- create-member|grant-role|revoke-role ..."""
    return {
        "actions": [f"cd {BACKEND} && uv run python -m sws_membership.manage %(args)s"],
        "params": [{"name": "args", "long": "args", "default": "--help"}],
    }


def task_seed():
    """Fill the local database with made-up members (never real data)."""
    sample = "tmp/sample-members.csv"
    manage = f"cd {BACKEND} && uv run python -m sws_membership.manage"
    return {
        "actions": [
            "mkdir -p tmp",
            f"{manage} generate-sample-members ../{sample} --count 200",
            f"{manage} import-members ../{sample}",
            f"{manage} seed-catalog",
        ],
        "task_dep": ["migrate"],
    }
