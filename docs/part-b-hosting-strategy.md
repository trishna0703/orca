# Part B — Infrastructure and hosting strategy

## Decision summary

Use one codebase and three data planes, not country-specific product forks:

1. A **central managed-cloud cell** for Belmara and data that has no residency constraint.
2. An **Arnova in-country cell** for all personal data belonging to Arnovan residents.
3. A **Calduria in-country sensitive-data cell** for minor records and datasets that cannot reliably exclude minors.

Each cell uses the same immutable application images and infrastructure module. A small global control plane may coordinate deployments, but it must contain no resident personal data, payloads, database copies, logs, support exports, or backups. Country routing is server-controlled from trusted tenant/country configuration, never from an arbitrary client header.

```text
                         CI/CD control plane
                  build once, sign once, promote digest
                                  |
             +--------------------+--------------------+
             |                    |                    |
      Central cloud         Arnova country cell   Calduria country cell
      Belmara + low-risk     all Arnovan PII       minors / possible-minor data
      global workloads       local logs/backups    local images/logs/backups
             |                    |                    |
             +--------- anonymised/approved events ---+
                                  |
                         Command View aggregates
```

Prefer managed container hosting, managed PostgreSQL, managed object storage, managed key management, and managed monitoring in each location. If Arnova or Calduria has no compliant public-cloud region, contract a local managed hosting provider or colocation partner. One internal IT person should administer contracts and automation, not manually patch bespoke servers in three countries.

## Application topology

`Central` means the primary managed-cloud region. `Arnova cell` and `Calduria cell` mean storage, backups, audit data, and any payload-bearing telemetry remain physically in that country.

| Application | Arnova | Belmara | Calduria | Rationale |
| --- | --- | --- | --- | --- |
| Landscape Intel | Central public/org dataset; Arnova-local identity and audit | Central | Central | The domain data is low sensitivity and non-personal. Arnovan operator profiles, access logs, and free text that could identify a person stay in Arnova. |
| Field Watch | Arnova cell | Central, isolated high-sensitivity boundary | Calduria cell for raw images and identifiable detections; central only for approved de-identified hotspot facts | Images may contain faces or children and are biometric-adjacent. Raw media, thumbnails, embeddings, EXIF, and person-linked detections inherit the strictest applicable placement. |
| Partner Engage | Arnova cell | Central | Central, with a business rule preventing minor contact records | Partner contacts are personal data even though the application is rated low sensitivity. Caldurian partner contacts are expected to be adults; exceptions must route to the Calduria cell. |
| Entity Setup | Arnova cell | Central | Central | Legal-entity data is low sensitivity, but signatory/director contact data makes the Arnovan workload personal. Minor records are not expected in this workflow. |
| Talent Pipeline | Arnova cell | Central | Calduria cell | Candidate records are PII and recruitment can include under-18 candidates. Keeping all Caldurian candidate PII together avoids fragile age-based record splitting. |
| Learn Path | Arnova cell for staff identities/progress; static course assets may be central | Central, protected survivor-learner dataset | Calduria cell for learner identity and progress; cacheable course assets may be central | Arnova is staff-only but still contains personal data. Belmara and Calduria serve survivor-learners; Caldurian learners may be minors. |
| Care Companion | Arnova cell | Central, isolated highest-sensitivity boundary | Calduria cell for all cases | All Arnovan resident data must remain local. In Calduria, keeping complete household/case records together is safer than separating minors from linked adults. |
| Command View | Central aggregate store; receives only disclosure-controlled metrics | Central | Central aggregate store; optional local read cache for connectivity | It contains anonymised counts only. Country cells publish schema-validated aggregates with small-cell suppression; no case IDs, images, names, precise coordinates, or free text cross the boundary. |

Every regional cell also contains the shared identity/RBAC records needed for its resident users, the relevant audit trail, outbox state, encryption keys, and in-country backups. Central observability receives health metrics and redacted technical diagnostics only.

## Required judgment calls

### Field Watch in Calduria

Treat raw Field Watch data as subject to the minors rule. A field image can capture a child even when the operator is mapping a location, and thumbnails, face-like embeddings, precise coordinates, timestamps, or analyst notes can preserve that link. At ingestion, age is usually unknown; “not labelled as a minor” is not evidence that no minor is present.

Raw images and identifiable derivatives therefore remain in the Calduria cell. A separate transformation may publish a central hotspot fact only after removing media, person/household identifiers, biometric features, exact device/operator identifiers, and unnecessary location precision. The published contract should contain fields such as country, coarse area, risk category, confidence band, and observation window. Privacy review and automated contract tests gate that export.

### Care Companion in Belmara

Host Belmara centrally. “No legal residency requirement” does not lower the security standard, but creating another regional stack does not by itself improve security and would burden the single support person. Put Care Companion in a separate high-sensitivity account/project and database boundary with least-privilege access, encryption using dedicated keys, private networking, short operational-log retention, tightly controlled support access, and tested recovery.

Belmara's seven-year audit requirement is handled separately: stream append-only audit records to retention-locked/WORM object storage in a security-controlled account. Store signed batch manifests and hash chains so deletion or alteration is detectable. The searchable database copy is convenient, but it is not the compliance archive.

### Operating regional infrastructure with one IT person

- Build one parameterised infrastructure-as-code module for all cells; differences are configuration (location, capacity, retention, keys), not copied templates.
- Build an application artifact once and promote the exact signed digest everywhere. Never rebuild per country.
- Use managed database, storage, secrets, certificate, backup, and monitoring services where locally available.
- Contract local hands/managed-service support for physical failures or provider escalation. A single employee cannot provide credible 24/7 support for in-country hardware.
- Automate database migrations as a gated release step, smoke tests after deployment, backup verification, certificate rotation, patch windows, and policy checks.
- Use a deployment dashboard/runbook that reports every cell, while keeping payload logs inside their residency boundary.
- Release progressively: central staging, low-risk production canary, Belmara, Arnova, then Calduria when connectivity permits. A failed cell pauses independently without creating a code fork.

## Connectivity and offline operation

Calduria's 3–5 day outages cannot be solved merely by putting a server in-country. Field-facing clients need an encrypted local queue, stable client-generated UUIDs, idempotency keys, resumable/chunked media upload, explicit sync state, and deterministic conflict handling. Cache the minimum data needed for assigned work; protect it with device encryption, MDM, expiry, remote wipe, and re-authentication policy.

Field Watch should perform safe capture validation and, where feasible, preliminary analysis on-device, then upload original media when connected. Care Companion must define field-level conflict rules rather than use last-write-wins for safeguarding, status, or assignment changes. Connectivity simulation for 5-day offline/reconnect scenarios is a release gate for both priority applications.

Arnova's rural sites use the same sync protocol where needed. This avoids a country-only implementation and makes offline behavior a reusable platform capability.

## Security, resilience, and retention

- Encrypt in transit and at rest; use separate keys, service identities, databases/buckets, and backup policies per cell and sensitivity tier.
- Keep production access just-in-time, MFA-protected, approved, and audited. Vendor support receives no standing data access.
- Keep backups inside the originating residency boundary and test restoration. Use multi-zone deployment where a compliant provider offers it.
- Apply data minimisation and explicit retention to images, offline device caches, recruitment records, and case attachments.
- Use WORM retention for all Belmara audit logs for seven years. Applying the same tamper-evident audit export pattern elsewhere simplifies operations, but each archive remains in its permitted location.
- Threat-model the de-identification gateway and test that cross-cell events contain only allow-listed fields.

## CI/CD and environments

### Pipeline

1. Pull request: formatting, static checks, unit/integration tests, migration checks, dependency and secret scanning, and API/event-contract compatibility tests.
2. Main branch: build one immutable container set, generate an SBOM, scan and sign it, then deploy that digest to integration.
3. Promotion: approval promotes the same digest to staging and progressively to production cells. Environment configuration and secrets come from each cell's secret manager.
4. Deployment: run backward-compatible migrations first, deploy with health checks, execute smoke tests, and support automated rollback of application code. Destructive migrations require a separate expand/migrate/contract release sequence.
5. Evidence: retain deployment approvals, artifact provenance, test results, and cell-by-cell rollout status.

### Environment strategy

| Environment | Purpose | Data policy |
| --- | --- | --- |
| Developer/ephemeral | Fast feature validation per branch | Synthetic data only; no production exports |
| Shared integration | Cross-app API and event-contract testing | Synthetic multi-country scenarios |
| Staging | Production-like release, migration, offline-sync, and recovery validation | Synthetic or irreversibly anonymised data; residency routes enabled |
| Production | Central, Arnova, and Calduria cells | Real data routed by the topology above |

Avoid eight-app-by-three-country persistent non-production stacks. Ephemeral namespaces and a shared synthetic integration environment keep cost and support load manageable. Maintain production-like regional staging capability through the same infrastructure module, creating it on demand for residency, migration, and disaster-recovery exercises.

## Decisions to validate before procurement

1. Obtain counsel's written interpretation of Arnovan “stored” data, including backups, logs, support exports, and disaster recovery.
2. Confirm whether Calduria treats identifiable imagery, inferred age, biometric templates, and linked household records as records belonging to minors.
3. Verify compliant managed-provider availability and multi-zone/backup options inside Arnova and Calduria; if absent, price a local managed-hosting contract rather than assuming one IT person can operate on-premises alone.
4. Agree the anonymisation threshold and small-cell suppression policy with safeguarding and programme leads.
5. Define application-specific retention, recovery objectives, and offline conflict rules before go-live.
