# Dairy farm and laboratory models

Initial Django setup with Python 3.12, Django 5.2 and PostgreSQL 17. The project contains models, managers, a revision creation service, basic Django Admin, migrations and model tests.

```text
config/       Settings, URLs, ASGI, WSGI and abstract TimeStampedModel
accounts/     User, UserManager, FarmMembership, admin, migrations and tests
manage/       Farm, Cow, MilkingLineGroup, MilkingLineItem, admin, migrations and tests
laboratory/   Microorganism, SampleBatch, Sample, SampleResult, Analysis,
              AnalysisRevision, Report, services, admin, migrations and tests
manage.py
```

## Setup

Create `.env` from the existing `.env example` file and set `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DB_NAME`, `DB_USERNAME`, `DB_PASS`, `DB_HOST` and `DB_PORT`. Use `DB_HOST=db` and `DB_PORT=5432` inside Compose. Use a new database for the initial custom user setup.

```bash
cp '.env example' .env
docker compose build web
docker compose up -d db
docker compose run --rm --entrypoint python web manage.py makemigrations accounts manage laboratory --no-header
docker compose run --rm --entrypoint python web manage.py migrate
docker compose run --rm --entrypoint python web manage.py check
docker compose run --rm --entrypoint python web manage.py test
docker compose run --rm --entrypoint python web manage.py createsuperuser
```

To run the existing Docker stack and access the basic Admin:

```bash
docker compose up -d
```

The entrypoint applies migrations and collects Django Admin static assets. The application uses `config.settings`, `AUTH_USER_MODEL = "accounts.User"`, UUID primary keys and timezone-aware timestamps in UTC. PostgreSQL configuration comes from environment variables. Django 5.2 requires PostgreSQL 14 or newer; Compose uses PostgreSQL 17.

## Analysis revisions

Create revisions through the service, which locks the analysis inside an atomic transaction and allocates the next version:

```python
from laboratory.services import create_analysis_revision

revision = create_analysis_revision(
    analysis=analysis,
    created_by=user,
    summary="Analysis summary",
    technical_notes="Technical observations",
    recommendations="Recommendations",
)
```

The first revision uses version 1. Subsequent revisions advance the version and update `Analysis.current_version`. The model also locks the analysis and synchronizes its version when a revision is saved directly. Saving an existing revision raises `ValidationError`. The Admin exposes revisions for inspection only; use the service to create them. Django bulk operations and raw SQL bypass model `save()` and must not be used to change revisions.

Email normalization follows Django's `BaseUserManager.normalize_email`, preserving the local part and lowercasing the domain. Native Groups and Permissions remain available. Users created through the basic Admin receive an unusable password; use `createsuperuser`, `changepassword`, or `UserManager` for password setup.

Reports reference a specific revision. Cross-farm relationships and report batch consistency are validated with `full_clean()` on save. Important and historical references use `PROTECT`. Dependent records use `CASCADE` as specified. No report generation or PDF implementation is included.

## Existing database preservation

The local setup previously used PostgreSQL 13 and migrations for Django's default user. The new setup uses database `dairy_management` and the separate `dairy_postgres_data` volume. The original `postgres_data` volume is preserved. This is a fresh schema; previous data has not been migrated. Do not attach the PostgreSQL 13 data volume directly to PostgreSQL 17.
