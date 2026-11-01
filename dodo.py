"""Every top-level action, for developers and CI alike. Run `uv run doit list`."""

# JSON state: the default dbm backend takes an exclusive lock, so `doit api`
# in one terminal would block `doit web` in another.
DOIT_CONFIG = {"default_tasks": ["check"], "verbosity": 2, "backend": "json", "dep_file": ".doit.json"}

BACKEND = "backend"
MANAGE = f"cd {BACKEND} && uv run python manage.py"


def task_db_up():
    """Start the local Postgres container."""
    return {"actions": ["docker compose up -d postgres"]}


def task_db_down():
    """Stop the local Postgres container, keeping its data."""
    return {"actions": ["docker compose stop postgres"]}


def task_db_reset():
    """Drop and recreate the local development database (made-up data only)."""
    psql = "docker compose exec -T postgres psql -U sws -d postgres -c"
    return {
        "actions": [
            f'{psql} "DROP DATABASE IF EXISTS sws_membership WITH (FORCE)"',
            f'{psql} "CREATE DATABASE sws_membership"',
        ],
        "task_dep": ["db_up"],
    }


def task_migrate():
    """Apply database migrations to the configured database."""
    return {"actions": [f"{MANAGE} migrate"]}


def task_makemigrations():
    """Write migrations for model changes (then review them before committing)."""
    return {"actions": [f"{MANAGE} makemigrations"]}


def task_api():
    """Run the API with reload on the local machine."""
    return {"actions": [f"{MANAGE} runserver 8000"]}


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
    """Operator commands: uv run doit manage --args "create_member EMAIL FIRST LAST" (see manage.py help)."""
    return {
        "actions": [f"{MANAGE} %(args)s"],
        "params": [{"name": "args", "long": "args", "default": "help"}],
    }


def task_seed():
    """Fill the local database with made-up members (never real data)."""
    sample = "tmp/sample-members.csv"
    return {
        "actions": [
            "mkdir -p tmp",
            f"{MANAGE} generate_sample_members ../{sample} --count 200",
            f"{MANAGE} import_members ../{sample}",
            f"{MANAGE} seed_catalog",
        ],
        "task_dep": ["migrate"],
    }
