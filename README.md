# Dairy farm and laboratory models

Initial Django setup with Python 3.12, Django 5.2 and PostgreSQL 17. The project contains models, managers, a revision creation service, basic Django Admin, JWT authentication endpoints, migrations and model and feature tests.

```text
config/       Settings, URLs, ASGI, WSGI and abstract TimeStampedModel
accounts/     User, UserManager, FarmMembership, JWT views, serializers, URLs,
              admin, migrations, model tests and authentication feature tests
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

Reports reference a specific revision. Cross-farm relationships and report batch consistency are validated with `full_clean()` on save. Important and historical references use `PROTECT`. Dependent records use `CASCADE` as specified. Report generation, publication and snapshot history are documented below.

## Existing database preservation

The local setup previously used PostgreSQL 13 and migrations for Django's default user. The new setup uses database `dairy_management` and the separate `dairy_postgres_data` volume. The original `postgres_data` volume is preserved. This is a fresh schema; previous data has not been migrated. Do not attach the PostgreSQL 13 data volume directly to PostgreSQL 17.

## JWT authentication

DRF uses `JWTAuthentication` and `IsAuthenticated` by default. Public authentication endpoints explicitly use `AllowAny`. Login uses the custom user's `email` and `password`; no username field is accepted as a substitute.

| Method | Endpoint | Request body | Authentication |
| --- | --- | --- | --- |
| POST | `/api/auth/login/` | `{"email": "farmer@example.com", "password": "password"}` | Public |
| POST | `/api/auth/refresh/` | `{"refresh": "refresh-token"}` | Public |
| POST | `/api/auth/logout/` | `{"refresh": "refresh-token"}` | Public |
| GET | `/api/auth/me/` | None | `Authorization: Bearer access-token` |

Login and refresh return `access` and `refresh`. Access tokens last 15 minutes and refresh tokens last 7 days. Refresh rotates the token and blacklists the submitted refresh token. Clients must replace their stored refresh token with the returned token after every refresh. Logout blacklists the submitted refresh token and returns HTTP 200 with an empty JSON object. Invalid or blacklisted tokens return HTTP 401. Existing access tokens remain valid until expiration after logout.

Custom claims are `name`, `email` and `is_superuser`. They are added to the refresh token and inherited by its access tokens. No farms or memberships are included. Claims reflect the user at login; the protected `me` endpoint reads the current database record. Django permissions must use the authenticated database user rather than trust client-side claims.

Rebuild the container after adding dependencies and apply the built-in blacklist migrations:

```bash
docker compose build web
docker compose run --rm --entrypoint python web manage.py migrate
docker compose run --rm --entrypoint python web manage.py check
docker compose run --rm --entrypoint python web manage.py test accounts.tests.test_authentication
docker compose run --rm --entrypoint python web manage.py test
```

Expired blacklist records can be cleaned with `python manage.py flushexpiredtokens`. No scheduler is included. Farm creation, listing and updates are implemented. Farm deletion and laboratory CRUD endpoints are not included.

## Farm creation

`POST /api/v1/farms/` requires `Authorization: Bearer <access-token>` from an authenticated superuser. Regular users, including staff users without `is_superuser`, receive HTTP 403; requests without authentication receive HTTP 401. The explicit `IsSuperUser` permission checks the database user, not the JWT claim.

```json
{
  "name": "Boa Vista Farm",
  "owner_name": "John Silva",
  "city": "Cacule",
  "state": "BA",
  "phone": "77999999999",
  "notes": "",
  "admin": {
    "name": "John Silva",
    "email": "john@example.com",
    "password": "StrongPassword123!"
  }
}
```

A successful request returns HTTP 201 with `id`, `name`, `owner_name`, `owner_email`, `city`, `state`, `phone`, `notes`, `is_active`, `created_at` and `updated_at`. Neither the nested `admin` object nor its password is returned. Invalid data returns the standard DRF HTTP 400 field error format.

`manage.services.farm_service.create_farm_with_owner` creates the user through `UserManager`, then the farm, then its active owner membership inside a single atomic transaction. Failure at any step rolls back all new records. Users receive `is_superuser=False` and `is_staff=False`; farms and memberships are active. Client-supplied privilege, permission, role and audit fields cannot override backend values.

Owner email is normalized to lowercase. Case-insensitive duplicate detection occurs during validation; the `unique_user_email_case_insensitive` database constraint on `Lower(email)` also prevents concurrent duplicate inserts. Only known email uniqueness failures are translated to field errors; unrelated errors propagate after rollback. Existing email spelling and the JWT endpoints are preserved. Password validation uses the configured Django validators and the prospective user; hashing uses `create_user`.

The response uses an active owner membership loaded with `select_related("user")` and `Prefetch`, avoiding additional owner lookup queries during serialization. Farm listing and updates are described below; no delete route is provided.

The additional migration is `accounts/0002_user_email_case_insensitive`. Before applying it to another existing database, check for case-insensitive email duplicates and resolve them explicitly; the migration does not delete or merge users.

Run the farm creation feature tests with:

```bash
docker compose run --rm --entrypoint python web manage.py test manage.tests.test_farm_creation
```

## Change own password

Authenticated users can send `POST /api/auth/change-password/` with `Authorization: Bearer <access-token>` and the following JSON body:

```json
{
  "current_password": "OriginalPassword123!",
  "new_password": "UpdatedPassword456!"
}
```

The current password must match and the new password must pass Django's configured password validators. The endpoint updates only the authenticated user's password and returns HTTP 204 with an empty body. Invalid input returns HTTP 400; missing or invalid authentication returns HTTP 401. No user identifier is accepted to select another account. Both password fields are write-only.

## List, edit and inactivate farms

All operations require a JWT access token. Listing and creation require `IsSuperUser`. Editing ordinary farm fields allows either a superuser or a user with an active `FarmMembership` for the target farm, using `IsSuperUserOrFarmMember`. Only superusers may inactivate or reactivate a farm. Any membership role qualifies. A membership on another farm, an inactive membership or staff status alone does not grant edit access; those requests return HTTP 403. Missing or invalid authentication returns HTTP 401.

| Method | Endpoint | Operation |
| --- | --- | --- |
| GET | `/api/v1/farms/` | List farms |
| PATCH | `/api/v1/farms/<farm-id>/` | Update selected fields |
| PUT | `/api/v1/farms/<farm-id>/` | Update farm data; name is required |

Listing includes active and inactive farms by default, ordered by name and UUID. Filter with `?is_active=true` or `?is_active=false`. Results use DRF page-number pagination with `count`, `next`, `previous` and `results`; the default is 20 farms per page. `page_size` accepts up to 100, and `page` selects the page. Owner memberships and their users are prefetched to avoid a query per farm.

Members can edit `name`, `owner_name`, `city`, `state`, `phone` and `notes`. Only superusers can change `is_active`. A member attempting to change it receives HTTP 403 and no fields from that request are saved. An unchanged `is_active` value is accepted but is not written by member updates. Responses retain the farm detail format, including `owner_email`. UUID and audit timestamps are read-only. These endpoints do not update the owner account, its credentials or the membership.

To inactivate a farm, send the following as a superuser:

```http
PATCH /api/v1/farms/<farm-id>/
Authorization: Bearer <access-token>
Content-Type: application/json

{"is_active": false}
```

The farm, its owner account, memberships and historical data remain in the database. Inactivation changes only `Farm.is_active`; it does not disable the owner user's login. Reactivate with `{"is_active": true}`. Successful updates return HTTP 200, validation errors return HTTP 400 and unknown farm UUIDs return HTTP 404. DELETE is unsupported and returns HTTP 405 for an authenticated superuser.

## Cow BREAD

Cow endpoints require JWT authentication and either a superuser or an active membership on the farm in the URL. As with ordinary farm editing, any active membership role qualifies. Access is checked against current database memberships on every request. Farm status activation and inactivation remain restricted to superusers on the farm endpoint.

| Method | Endpoint | Operation |
| --- | --- | --- |
| GET | `/api/v1/farms/<farm-id>/cows/` | Browse cows on the farm |
| POST | `/api/v1/farms/<farm-id>/cows/` | Add a cow |
| GET | `/api/v1/farms/<farm-id>/cows/<cow-id>/` | Read a cow |
| PUT | `/api/v1/farms/<farm-id>/cows/<cow-id>/` | Edit cow data; name and identifier are required |
| PATCH | `/api/v1/farms/<farm-id>/cows/<cow-id>/` | Edit selected fields |
| DELETE | `/api/v1/farms/<farm-id>/cows/<cow-id>/` | Delete a cow without protected references |

Creation example:

```json
{
  "name": "Daisy",
  "identifier": "A2",
  "birth_date": "2022-05-01",
  "breed": "Holstein",
  "status": "active",
  "notes": "New cow"
}
```

`name` and `identifier` are required for creation. Status defaults to `active`; allowed values are `active`, `dry`, `sold` and `deceased`. Birth date is optional and nullable. The farm is assigned from the URL and cannot be changed by the payload. UUID and audit timestamps are read-only. Responses include `id`, `farm`, `name`, `identifier`, `birth_date`, `breed`, `status`, `notes`, `created_at` and `updated_at`.

Identifiers are unique within each farm, preserving the existing database constraint. The same identifier can be used on different farms. Duplicate validation errors, including conflicting concurrent writes, return HTTP 400 with an `identifier` error. Cow writes run through `manage/services/cow_service.py` in atomic transactions, and updates write only validated editable fields.

Browse is ordered by name and UUID and uses the same pagination format as farm listing: 20 records per page by default, with `page` and `page_size` up to 100. Filter by `?status=dry` or search names and identifiers with `?search=daisy`; filters may be combined.

Successful creation returns HTTP 201, reads and edits return HTTP 200, and successful deletion returns HTTP 204 with an empty body. Missing authentication returns HTTP 401; no active membership on the target farm returns HTTP 403. Unknown cows, or cows belonging to another farm accessed through an authorized farm URL, return HTTP 404.

Cow deletion respects existing `PROTECT` references. Cows with samples or milking line items return HTTP 409 with a `detail` error; the cow and related records remain intact. Cow deletion does not delete the farm, its users or memberships. Farm DELETE remains unsupported.

```bash
docker compose run --rm --entrypoint python web manage.py test manage.tests.test_cow_management
```

## App module layout

Tests, views and serializers live in packages inside their owning app. URL paths and permissions are unchanged.

```text
accounts/
  views/auth_views.py
  serializers/auth_serializers.py
  tests/test_models.py
  tests/test_authentication.py
  tests/test_password_change.py
manage/
  api/permissions.py
  api/urls.py
  views/farm_views.py
  views/cow_views.py
  serializers/farm_serializers.py
  serializers/cow_serializers.py
  services/farm_service.py
  services/cow_service.py
  tests/test_models.py
  tests/test_farm_creation.py
  tests/test_farm_management.py
  tests/test_cow_management.py
laboratory/
  tests/test_models.py
config/
  tests/test_startup.py
```

Each package contains `__init__.py`. Run all tests with `python manage.py test`, or select an app package with `python manage.py test accounts.tests`, `python manage.py test manage.tests` or `python manage.py test laboratory.tests`.

## Laboratory BREAD API

JWT-authenticated endpoints under `/api/v1/laboratory/`:

| Resource | Collection |
| --- | --- |
| Microorganism | `microorganisms/` |
| SampleBatch | `sample-batches/` |
| Sample | `samples/` |
| SampleResult | `sample-results/` |
| Analysis | `analyses/` |
| AnalysisRevision | `analysis-revisions/` |
| Report | `reports/` |

Collections support GET (browse) and POST (add). Append `<uuid>/` for GET (read), PUT/PATCH (edit), and DELETE on general laboratory resources. Reports use the restricted workflow documented below. Only superusers can write, including through Django Admin; staff status and farm roles do not grant write access. Regular users can read records belonging to farms where they have an active membership. Microorganisms are visible to these users only when referenced by results from their farms. Records outside their scope return 404. Anonymous requests return 401 and unauthorized writes return 403.

Lists use `page` and `page_size`, with 20 records by default and a maximum of 100, ordered by creation time and UUID. Creator fields, UUIDs and timestamps are assigned by the server. Revision versions and analysis current versions are managed automatically. Editing an analysis revision creates a new version and returns its new UUID; the original revision and reports referencing it remain intact. Revisions cannot be moved to another analysis. Protected deletions return 409; model validation errors return 400.

```bash
docker compose exec -T web python manage.py test laboratory --noinput
```

## Microbiological reports

Reports now use the existing Analysis and immutable AnalysisRevision history. Saving changed general analysis creates a new revision and moves only the draft report to it. Existing revisions are never overwritten. SampleResultAnalysis stores an explicit professional assessment for each result; BatchCowAssessment stores the cow assessment and milking position within a batch. Existing farm-wide MilkingLineGroup and MilkingLineItem remain independent of historical batch assessments.

Rebuild the PDF dependencies and migrate:

```bash
docker compose build web
docker compose up -d
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py makemigrations --check
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test
```

WeasyPrint uses local Django templates, Pango, HarfBuzz and DejaVu Sans. The Dockerfile installs the required Debian packages. For local Python development, install `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core` using your OS package manager, then `pip install -r requirements.txt`. See the [WeasyPrint installation documentation](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html). No external renderer or remotely loaded resource is used.

Set `MEDIA_ROOT` to a writable directory; its default is `BASE_DIR / "media"`, mounted on the `report_media` Compose volume. `MEDIA_URL` is `/media/`. Reports must be delivered by the authenticated download endpoint; do not expose the reports directory through a public media server or public S3 bucket. FileField uses the configured Django storage, including private S3-compatible backends configured through Django `STORAGES`. Database values are storage keys, never absolute paths. The download endpoint opens the file through storage after authorization.

Configure the laboratory using `REPORT_LABORATORY_NAME`, `REPORT_LABORATORY_CITY`, `REPORT_LABORATORY_STATE`, `REPORT_LABORATORY_CONTACT`, and `REPORT_SYSTEM_NAME`. Optionally set `REPORT_LOGO_PATH` to a trusted local PNG or JPEG file inside the container. The logo is embedded into the snapshot, and all texts are escaped. The PDF renderer allows only embedded image resources. Responsible professional name, registration and report date are entered per revision. No copied logo, signature, third-party contact, medication, dosage or automatic clinical recommendation is supplied.

All endpoints below are relative to `/api/v1/laboratory/` and require JWT authentication:

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `batches/<batch-id>/report-data/` | Superuser editor data, grouped by cow; optional `?report=<id>` selects its general revision |
| POST | `batches/<batch-id>/reports/` | Create a draft, deriving the farm from the batch |
| GET | `reports/` | Paginated authorized reports; filters `farm`, `batch`, `status`, `date_from`, `date_to` (collection dates) |
| POST | `reports/` | Compatibility creation endpoint; requires `batch` |
| GET | `reports/<id>/` | Authorized report details and snapshot |
| PATCH | `reports/<id>/` | Superuser draft update |
| POST | `reports/<id>/generate/` | Validate and generate the immutable PDF input snapshot |
| POST | `reports/<id>/publish/` | Publish a generated version |
| POST | `reports/<id>/new-version/` | Create another draft using the previous general revision |
| GET | `reports/<id>/preview/` | Escaped HTML preview; generated/published reports use their stored snapshot |
| GET | `reports/<id>/download/` | Authorized FileResponse with PDF content type and safe attachment filename |

Draft PATCH accepts `title`, `general_analysis`, `result_analyses`, and `cow_assessments`. General analysis accepts `summary`, `technical_notes`, `recommendations`, `management_notes`, `responsible_name`, `professional_registration`, and `report_date`. Each result analysis accepts `sample_result`, `classification`, `interpretation`, `recommendation`, and `treatment_notes`. Each cow assessment accepts `cow`, `clinical_status`, `general_notes`, `milking_group`, and nullable `milking_position`. All referenced results and cows must be in this batch. Duplicate positions within a group are rejected; swapping positions is supported atomically. Farm, file, snapshot, status and audit fields cannot be assigned through PATCH.

Only active superusers can mutate reports or technical assessments. Staff status and membership roles do not grant these operations. Common users can only read published reports with an active FarmMembership on the batch farm. Querysets, object permission checks and sensitive services enforce access. Downloads apply the same scope before opening storage. Report DELETE is unsupported. Report Admin is inspection-only. Cancelled reports are hidden from members; cancellation is currently an internal state without a public transition endpoint.

Generation requires results for all samples, individual classifications, cow clinical status and milking groups, and a responsible professional with registration. No treatment or recommendation is required or inferred. Versions are allocated under a batch lock and constrained by `(batch, version)`. Generation locks the draft, builds the snapshot with five data-loading queries, and renders only that JSON snapshot. The snapshot contains laboratory identity, property, batch, samples, quarters, all result types, individual analyses, cow assessments, ordered milking groups and general analysis. The publication service locks the generated version, sets publication audit fields and freezes it. Corrections require a new report version with a new file. Changes to live cows, results or laboratory settings cannot alter an existing PDF. Do not use bulk updates or raw SQL to bypass model immutability checks.

Migration `laboratory/0002_microbiological_reports` adds the missing structures and numbers existing reports chronologically within each batch before adding the unique version constraint. It does not rewrite existing files or fabricate snapshots for legacy reports. Legacy generated/published reports without snapshots require review and a new generated version before relying on the historical snapshot guarantee.

### Development example and PDF inspection

With `DEBUG=True`, an existing superuser, and a development database only:

```bash
docker compose exec -T web python manage.py create_demo_report --user lab@example.com
```

This explicitly creates a separate demonstration farm, five cows, six samples from different quarters, positive/negative/inconclusive/contaminated results, multiple organisms on one cow, individual analyses, all four milking groups, and long Portuguese text. It generates a PDF without publishing it and prints its report UUID and storage key (`reports/YYYY/MM/microbiological-report-<uuid>-v1.pdf`). Re-running creates a separate example. Nothing is seeded during startup or migrations; the command refuses `DEBUG=False`.

Open `/reports/<report-id>` in the React app for the preview and PDF download; `/reports/<report-id>/edit` edits drafts and `/batches/<batch-id>/report` starts a new report. Open `/reports` to select a farm and batch. The preview uses the backend HTML; the backend snapshot is always the final PDF source.

To test download, authenticate and use the UI's **Baixar PDF**, or send `GET /api/v1/laboratory/reports/<report-id>/download/` with an access token supplied securely in the Authorization header. Expect `application/pdf`, an attachment filename and the `%PDF` signature. Keep credentials out of logs, shell history and shared artifacts.

Copy a generated example out of the container and inspect every page with Poppler:

```bash
docker compose cp web:/code/media/reports/YYYY/MM/microbiological-report-UUID-v1.pdf /tmp/microbiological-report-example.pdf
pdftoppm -r 120 -png /tmp/microbiological-report-example.pdf /tmp/microbiological-report-page
pdfinfo /tmp/microbiological-report-example.pdf
pdftotext -layout /tmp/microbiological-report-example.pdf /tmp/microbiological-report-example.txt
```

Inspect all PNGs for clipping, overlap, table width, page breaks, Portuguese characters, contrast, repeated header, footer and page numbering. A4 layout has repeating table headers, flowing content and no fixed page count. Use a further long-result case when changing table CSS.

Report tests:

```bash
docker compose exec -T web python manage.py test laboratory.tests.test_reports
docker compose exec -T web python manage.py test
```

A generated five-page example, all rendered PNGs, implementation notes and validation results are in [docs/microbiological-report-validation.md](docs/microbiological-report-validation.md).

## Replace local presentation records

`python manage.py reset_presentation_data --replace-operational-data` explicitly replaces operational records while preserving user accounts. It refuses `DEBUG=False`. Back up the database and media before running it. This command is intended only for a disposable local development database; it deliberately removes existing report versions and their files after the database transaction commits.

The presentation dataset contains two fictional farms, fourteen named cows with ear tags, two coded batches, eighteen samples, four microorganisms, explicit result assessments, milking groups and three report states (draft, generated and published). Non-superuser accounts receive an active membership only on Fazenda Boa Esperança. These are coherent fictional records, not actual laboratory findings. No professional registration, prescription, dosage or treatment is fabricated.

`GET /api/v1/farm-options/` provides farm names for selection, scoped by active memberships for regular users; it does not change permissions on the administrative farms collection. Laboratory read serializers include related display names. UUIDs remain internal API identifiers and are omitted from the PDF and download filename.
