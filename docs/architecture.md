# Construction OS — System Architecture

**Status:** Proposed for review  
**Scope:** Architecture only; no business functionality is implemented  
**Primary style:** Modular monolith

## 1. Goals and principles

Construction OS is a multi-tenant construction management platform that combines project structure, drawings, calculations, progress, procurement, workforce, photos, tasks, AI assistance, and an immutable audit trail.

The first production architecture is a modular monolith: one deployable backend with strict module boundaries, one primary relational database, one worker deployment, and shared object storage. This minimizes operational complexity while preserving a clear path to extract high-load modules later.

Core principles:

- tenant isolation at every persistence and authorization boundary;
- explicit module ownership of data and business rules;
- transactions inside the monolith; events for cross-module side effects;
- append-only audit and versioned calculation results;
- asynchronous processing for OCR, previews, AI, imports, and notifications;
- deterministic calculations separated from probabilistic AI;
- API-first design with idempotency for mutation and retry safety;
- least privilege and deny-by-default authorization.

## 2. Repository structure

```text
construction-os/
├── apps/
│   ├── api/                 # HTTP API composition root
│   ├── worker/              # background job composition root
│   └── web/                 # web client (future implementation)
├── packages/
│   ├── modules/
│   │   ├── identity/
│   │   ├── companies/
│   │   ├── projects/
│   │   ├── structures/
│   │   ├── documents/
│   │   ├── calculations/
│   │   ├── progress/
│   │   ├── tasks/
│   │   ├── materials/
│   │   ├── procurement/
│   │   ├── workforce/
│   │   ├── photos/
│   │   ├── ai/
│   │   └── audit/
│   ├── shared/
│   │   ├── auth/
│   │   ├── database/
│   │   ├── events/
│   │   ├── jobs/
│   │   ├── observability/
│   │   ├── storage/
│   │   └── validation/
│   ├── contracts/           # API schemas and domain-event contracts
│   └── calculation-engine/  # deterministic calculation core
├── infrastructure/
│   ├── containers/
│   ├── migrations/
│   ├── deployment/
│   └── monitoring/
├── tests/
│   ├── architecture/
│   ├── integration/
│   ├── contract/
│   └── e2e/
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── ai.md
│   └── deployment.md
└── README.md
```

The final language/framework may be selected after architecture approval. The boundaries above are framework-independent.

## 3. Backend architecture

Each business module contains:

```text
module/
├── domain/          # entities, value objects, policies, domain services
├── application/     # commands, queries, use cases, ports
├── infrastructure/  # repositories, adapters, persistence mappings
├── api/             # routes/controllers and request/response mapping
└── events/          # published/consumed event definitions
```

Dependency direction is `api -> application -> domain`; infrastructure implements application ports. Modules must not read another module's tables directly. They communicate through public application services for synchronous consistency or versioned domain events for asynchronous reactions.

### Module ownership

| Module | Owned entities | Responsibilities |
|---|---|---|
| Identity | User | authentication identity, sessions, user lifecycle |
| Companies | Company | tenant lifecycle, company settings, membership policy |
| Projects | Project, ProjectMember | project lifecycle, project access |
| Structures | Structure | hierarchical construction breakdown |
| Documents | Document, DocumentPage | upload, versions, page extraction, OCR metadata |
| Calculations | Calculation | inputs, engine execution, versions, approvals |
| Progress | ProgressEntry | measured work, reporting periods, evidence links |
| Tasks | Task | assignment, dependencies, status workflow |
| Materials | Material, MaterialRequirement | catalog and quantified requirements |
| Procurement | PurchaseRequest | request workflow and fulfillment tracking |
| Workforce | Worker, Crew | people, crew membership, allocation |
| Photos | Photo | media metadata and links to project objects |
| AI | AIConversation, AIMessage | grounded conversations and tool orchestration |
| Audit | AuditEvent | immutable business/security history |

### Cross-module event flow

Events are recorded in an outbox in the same database transaction as the business change. A worker publishes and handles them at least once. Consumers must be idempotent.

Examples:

- `DocumentUploaded` -> virus scan -> page extraction -> OCR -> index update;
- `CalculationApproved` -> material requirements proposal;
- `ProgressEntryApproved` -> project progress aggregate refresh;
- `MaterialRequirementApproved` -> purchase request proposal;
- `PhotoUploaded` -> metadata extraction and thumbnail generation;
- every security-sensitive change -> `AuditEvent`.

## 4. Entity relationships

The detailed relational model is in `database.md`. Principal relationships are:

- Company has many Users through company membership policy and many Projects.
- Project belongs to Company and has many ProjectMembers.
- ProjectMember associates a User with a Project role.
- Structure belongs to Project and optionally to a parent Structure.
- Document belongs to Project, can target a Structure, and has many DocumentPages.
- Calculation belongs to Project, can target a Structure and reference Documents/pages.
- ProgressEntry belongs to Project and normally references a Structure; it may reference a Task, Calculation, workers, crews, and photos.
- Task belongs to Project, optionally a Structure, and may be assigned to a User, Worker, or Crew.
- Material is company-scoped; MaterialRequirement belongs to Project and may originate from a Calculation.
- PurchaseRequest belongs to Project and contains requested MaterialRequirements/items.
- Worker belongs to Company; Crew belongs to Company and can be allocated to Projects.
- Photo belongs to Project and can be attached through typed link records to structures, progress, tasks, and documents.
- AIConversation belongs to Company and Project; AIMessage belongs to a conversation.
- AuditEvent is company-scoped and records actor, action, target, context, and safe change metadata.

## 5. Roles and authorization

Authorization combines company role, project role, resource scope, and action policy.

### Company roles

| Role | Main authority |
|---|---|
| Company Owner | full tenant control, billing/settings, ownership transfer |
| Company Admin | users, projects, catalogs, policies; no ownership transfer |
| Company Auditor | read-only access including audit and approved records |
| Company Member | only explicitly assigned projects |

### Project roles

| Role | Main authority |
|---|---|
| Project Manager | full project operations and member management |
| Chief Engineer | technical approval of documents/calculations/progress |
| Site Manager | daily operations, workforce, tasks, progress |
| Engineer | create/edit technical records and calculations |
| Procurement Manager | materials and purchase requests |
| Foreman | crew tasks, progress entries, site photos |
| Viewer | read-only project access |

Rules:

- company access never implies access to another company;
- project access requires active ProjectMember unless company policy explicitly grants it;
- approval actions are separate permissions from edit actions;
- a user cannot approve their own protected record when four-eyes control is enabled;
- audit history cannot be edited by application roles;
- worker records are not authentication accounts unless separately linked to a User.

Permission examples use `resource.action`, such as `document.upload`, `calculation.approve`, `progress.verify`, `purchase_request.approve`, and `audit.read`.

## 6. API structure

Base path: `/api/v1`. JSON uses stable IDs, ISO-8601 UTC timestamps, decimal quantities as strings, cursor pagination, and structured errors.

```text
/auth/*
/me
/companies
/companies/{companyId}/members
/companies/{companyId}/materials
/companies/{companyId}/workers
/companies/{companyId}/crews
/projects
/projects/{projectId}/members
/projects/{projectId}/structures
/projects/{projectId}/documents
/projects/{projectId}/calculations
/projects/{projectId}/progress-entries
/projects/{projectId}/tasks
/projects/{projectId}/material-requirements
/projects/{projectId}/purchase-requests
/projects/{projectId}/photos
/projects/{projectId}/ai/conversations
/projects/{projectId}/audit-events
/jobs/{jobId}
```

API conventions:

- OpenAPI is the contract source of truth;
- mutation endpoints accept `Idempotency-Key`;
- optimistic concurrency uses `version` or `If-Match`;
- long operations return `202 Accepted` with a job resource;
- upload initiation returns a short-lived presigned URL;
- filtering is allow-listed, not passed directly to the database;
- validation errors contain field paths and machine-readable codes;
- request correlation IDs propagate through jobs and audit events;
- webhooks, if added, are signed and retried from an outbox.

## 7. Storage architecture

- PostgreSQL: authoritative transactional and relational state.
- S3-compatible object storage: original documents/photos, rendered pages, thumbnails, exports.
- Redis: rate limits, short-lived cache, job coordination; never authoritative state.
- Search index: optional derived full-text/vector index; PostgreSQL can serve the first release.
- Queue: managed queue or Redis-backed queue initially; payloads contain IDs, not large files.

Object keys are generated server-side and include environment, company, project, object type, immutable object ID, and version. Database metadata is written before upload finalization. Objects remain quarantined until checksum, content-type, size, and malware checks pass. Downloads use authorized, short-lived signed URLs.

## 8. Calculation engine architecture

The calculation engine is an isolated deterministic package. AI may extract or propose input data but cannot directly approve or silently change a calculation.

Pipeline:

1. load versioned input schema and referenced geometry;
2. normalize units to canonical SI values;
3. validate completeness, ranges, and geometry consistency;
4. execute a version-pinned calculation method;
5. produce result values, warnings, assumptions, and trace steps;
6. persist immutable input and result snapshots with engine version;
7. require human review/approval where configured;
8. derive material requirements only from an approved version.

Calculation records retain `engine_version`, `input_schema_version`, unit system, rounding policy, source references, and content hashes. Golden tests, property tests, and reference engineering cases are release gates.

## 9. Background jobs

| Job | Trigger | Retry/dead-letter policy |
|---|---|---|
| File malware scan | upload finalized | retry transient failures; quarantine on terminal failure |
| Document page extraction | safe document | retry; page-level resume |
| OCR and text extraction | page created | retry per page; preserve confidence |
| Preview/thumbnail generation | safe media | retry; regenerate deterministically |
| AI ingestion/indexing | extracted text changed | idempotent upsert by content hash |
| Calculation execution | calculation submitted | no duplicate version; terminal validation errors |
| Progress aggregation | approved progress event | idempotent project-period refresh |
| Notification delivery | business event | exponential backoff and dead letter |
| Export/report generation | user request | expiring artifact and status resource |
| Retention cleanup | schedule | policy-controlled, audit recorded |
| Outbox dispatch | committed transaction | retry until delivered/handled |

Every job has a stable type, schema version, correlation ID, tenant/project IDs, attempt count, and idempotency key. Workers use leases and bounded concurrency.

## 10. Audit system

Audit events are append-only and record:

- event ID and UTC timestamp;
- company/project scope;
- actor type and actor ID;
- action and target type/ID;
- request, correlation, session, and job IDs;
- outcome and policy decision;
- safe before/after field diff or change summary;
- source IP/user-agent where legally appropriate;
- integrity metadata.

Secrets, access tokens, raw passwords, full binary content, and unrestricted AI prompts are never placed in audit payloads. Database permissions deny application updates/deletes. Periodic export to immutable retention storage is recommended for high-assurance deployments.

## 11. Observability and quality gates

- structured logs with redaction and correlation IDs;
- metrics for latency, errors, queue delay, retries, storage, OCR/AI cost, and calculation failures;
- distributed traces across API, worker, storage, and model calls;
- module dependency tests prevent forbidden imports;
- migration, API contract, authorization, tenant-isolation, and backup-restore tests;
- SLOs defined for API availability, job completion, and recovery objectives.

## 12. Technical risks

| Risk | Impact | Mitigation |
|---|---|---|
| Tenant data leakage | Critical | company-scoped keys, policy checks, row-level defense, isolation tests |
| Incorrect engineering calculation | Critical | deterministic engine, versioning, trace, golden cases, approval workflow |
| AI hallucination | High | retrieval citations, tools with schemas, confidence, human approval, no silent writes |
| Poor drawing/OCR quality | High | retain originals, confidence and page coordinates, manual correction workflow |
| Modular monolith erosion | High | module ownership, dependency tests, no cross-table access |
| Large documents/media | High | direct multipart upload, asynchronous processing, quotas and streaming |
| Event duplication/out-of-order delivery | Medium | transactional outbox, idempotent consumers, version checks |
| Complex authorization | High | centralized policy engine, permission matrix, deny-by-default tests |
| Schema churn | Medium | additive migrations, versioned contracts, expand/migrate/contract rollout |
| Vendor lock-in | Medium | storage/model adapters, portable data exports, provider-neutral domain layer |
| Audit growth/privacy conflict | Medium | partitioning, retention policy, payload minimization, legal review |
| Premature service extraction | Medium | measure first; extract only clear scaling/ownership bottlenecks |

## 13. Architecture approval gates

Implementation must not start until reviewers approve:

1. tenant and project authorization model;
2. entity ownership and database constraints;
3. calculation traceability and approval policy;
4. document/photo retention and security;
5. AI data-handling and human-control boundaries;
6. deployment target, recovery objectives, and operating budget.

