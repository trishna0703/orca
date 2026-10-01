# Part A requirement traceability

This matrix links the assignment's Part A requirements to the current ORCA implementation and verification evidence.

| Assignment requirement | Implementation evidence | Verification evidence | Status |
| --- | --- | --- | --- |
| Shared data-layer pattern used by two application domains | `app/models/base_entity.py`; `Case` in `app/models/case.py`; `Partner` in `app/models/partner.py` | `tests/test_models.py`; `tests/test_partner.py` | PASS |
| RBAC across both entity types, scoped by application and permission without role-name checks | `app/authorization/service.py`; `app/authorization/dependencies.py`; Care Companion and Partner Engage route dependencies in `app/api/v1/` | `tests/test_authorization.py`; `tests/test_case_api.py`; `tests/test_partner.py` | PASS |
| Country scope enforced at the query layer | Shared `apply_entity_scope` adds owner application, allowed-country, and non-deleted predicates; both `case_repository.py` and `partner_repository.py` apply it before execution | SQL-construction and visibility tests in `tests/test_authorization.py`, `tests/test_case_api.py`, and `tests/test_partner.py` | PASS |
| Generic reusable audit trail | `app/models/audit_log.py`, `app/audit/service.py`, and `app/audit/serializers.py` are used by both domain services; mutation and audit commit in one service-owned transaction | `tests/test_audit.py`, `tests/test_audit_serializer.py`, and Partner audit assertions | PASS |
| One real cross-application integration | Case mutations write versioned outbox records; the generic processor dispatches `case.created.v1` and `case.closed.v1`; Command View handlers update their own projection table | End-to-end create/process/close/process assertions in `tests/test_command_view.py` | PASS |
| API contract for another application team | FastAPI generates `/openapi.json`; request/response schemas and route metadata cover Care Companion, Partner Engage, Command View, Audit, and Platform | OpenAPI loads through `app/main.py`; Swagger at `/docs` and ReDoc at `/redoc` | PASS |

## Architectural fit

- Repositories perform data access and never own commits.
- Services coordinate domain changes, audit records, and outbox records in a single PostgreSQL transaction.
- Command View reads its projection instead of querying the Care Companion `cases` table.
- Partner Engage proves reuse without Partner-specific audit or event infrastructure.
- Development `X-User-Id` authentication is intentionally separate from authorization; production identity is outside Part A.

The current full suite baseline is **52 passing tests**. The known optimistic-concurrency hardening item described in project context is a production improvement, not a missing Part A requirement.
