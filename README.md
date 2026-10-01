# ORCA Platform Backend

## What ORCA is

ORCA is a FastAPI and PostgreSQL modular monolith that supplies shared backend capabilities to domain applications. Care Companion manages cases, Partner Engage manages partners, and Command View consumes integration events to maintain country-level case metrics.

## Architecture

```text
                         ORCA API
                            |
          +-----------------+-----------------+
          |                 |                 |
  Care Companion     Partner Engage       Audit API
       Case              Partner         AuditLog reads
          |                 |
          +------- BaseEntity + RBAC + SQL country scope
          |
     OutboxEvent -- process_outbox.py --> Command View projection
```

Routes delegate to services for transaction and domain coordination, then to repositories for SQL access. Application ownership and country scope remain explicit throughout this path.

## Shared `BaseEntity` pattern

`Case` and `Partner` are separate typed SQLAlchemy models and tables, but both inherit `BaseEntity`. The base supplies UUID identity, `country_id`, `owner_app_id`, creation/update metadata, soft-delete metadata, and optimistic `version`. This demonstrates reuse without an EAV model or a runtime-generated entity framework.

## RBAC and country scoping

Permissions are application-owned and attached to roles through data, not hardcoded role checks. FastAPI dependencies resolve the current user and application and verify the required permission. Repositories call the shared `apply_entity_scope` helper, which adds these predicates before SQL execution:

```sql
owner_app_id = :application_id
AND country_id IN (:allowed_country_ids)
AND deleted_at IS NULL
```

The development API identifies a seeded user through `X-User-Id`; this is intentionally demo authentication, not production identity.

## Audit trail

The reusable audit service records actor, application, entity type and ID, country, request ID, and before/after snapshots. Domain mutations and their `AuditLog` rows use the same SQLAlchemy session and commit atomically. Case and Partner services share this implementation.

## Transactional outbox

Care Companion writes versioned `OutboxEvent` rows in the same transaction as Case mutations and audit records. The processor claims pending rows, dispatches registered handlers, and records processed events for idempotency. No broker or additional service is required for this submission.

## Care Companion to Command View flow

`case.created.v1` increments the country projection's `open_count`. `case.closed.v1` decrements the previous status count and increments `closed_count`. Command View reads only its projection table; it does not query Care Companion's `cases` table.

## Partner Engage: second-domain proof

Partner Engage adds `Partner` using the same BaseEntity, route-service-repository, permission, SQL-scope, and generic-audit patterns as Case. Its API supports create, list, get, and update. Partner does not emit outbox events because no Partner integration is required.

## Local setup

Prerequisites are Docker and [uv](https://docs.astral.sh/uv/).

```bash
docker compose up -d
uv sync --all-extras
```

Copy `.env.example` to `.env` if the default local PostgreSQL connection needs changing.

### Migrations

```bash
uv run alembic upgrade head
```

### Seed

The idempotent seed creates the three applications, countries, demo users, permissions, roles, and country scopes.

```bash
uv run python -m scripts.seed
```

### Run the API

```bash
uv run uvicorn app.main:app --reload
```

Swagger is available at <http://localhost:8000/docs>, ReDoc at <http://localhost:8000/redoc>, and the generated contract at <http://localhost:8000/openapi.json>.

## Reproducible cross-application demo

With PostgreSQL seeded and the API running, execute this PowerShell sequence. It captures the initial Arnova metric, creates a Case, processes the existing outbox, closes the Case, and processes the outbox again.

```powershell
$aliceId = (docker compose exec -T postgres psql -U postgres -d orca -Atc "SELECT id FROM users WHERE email='alice@orca.internal'").Trim()
$arnovaId = (docker compose exec -T postgres psql -U postgres -d orca -Atc "SELECT id FROM countries WHERE code='ARN'").Trim()
$headers = @{ "X-User-Id" = $aliceId }

uv run python -m scripts.process_outbox
$before = Invoke-RestMethod http://localhost:8000/v1/command-view/case-metrics -Headers $headers | Where-Object country_id -eq $arnovaId
$beforeOpen = if ($null -eq $before) { 0 } else { $before.open_count }
$beforeClosed = if ($null -eq $before) { 0 } else { $before.closed_count }

$body = @{ title = "ORCA projection demo"; country_id = $arnovaId } | ConvertTo-Json
$case = Invoke-RestMethod http://localhost:8000/v1/cases -Method Post -Headers $headers -ContentType application/json -Body $body
uv run python -m scripts.process_outbox
$afterCreate = Invoke-RestMethod http://localhost:8000/v1/command-view/case-metrics -Headers $headers | Where-Object country_id -eq $arnovaId
"open_count: $beforeOpen -> $($afterCreate.open_count)"

Invoke-RestMethod "http://localhost:8000/v1/cases/$($case.id)/close?expected_version=$($case.version)" -Method Post -Headers $headers
uv run python -m scripts.process_outbox
$afterClose = Invoke-RestMethod http://localhost:8000/v1/command-view/case-metrics -Headers $headers | Where-Object country_id -eq $arnovaId
"open_count: $($afterCreate.open_count) -> $($afterClose.open_count); closed_count: $beforeClosed -> $($afterClose.closed_count)"
```

Expected deltas are `open_count + 1` after creation, then `open_count - 1` and `closed_count + 1` after closure.

## Tests

```bash
uv run pytest -q
```

Focused test modules cover models, authorization/scoping, audit atomicity, Case lifecycle/outbox behavior, Command View projection/idempotency, and Partner behavior.

## Assignment deliverables

- [Part A requirement traceability](docs/part-a-requirements-traceability.md)
- [Part B infrastructure and hosting strategy](docs/part-b-hosting-strategy.md)
