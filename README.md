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

Reports reference a specific revision. Cross-farm relationships and report batch consistency are validated with `full_clean()` on save. Important and historical references use `PROTECT`. Dependent records use `CASCADE` as specified. No report generation or PDF implementation is included.

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
docker compose run --rm --entrypoint python web manage.py test accounts.test_features
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
docker compose run --rm --entrypoint python web manage.py test manage.test_farm_creation
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
docker compose run --rm --entrypoint python web manage.py test manage.test_cow_management
```
