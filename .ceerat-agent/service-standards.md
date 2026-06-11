# Service Standards

This file gives the builder agent service-level rules for creating or modifying Ceerat backend services. It is based on the current `ceerat-user-service` docs, especially:

- `services-repo/services/ceerat-user-service/docs/architecture.md`
- `services-repo/services/ceerat-user-service/docs/api.md`
- `services-repo/services/ceerat-user-service/docs/grpc-security.md`
- `services-repo/services/ceerat-user-service/docs/logging.md`
- `services-repo/services/ceerat-user-service/docs/api-testing.md`
- `services-repo/services/ceerat-user-service/docs/new-service-cookbook.md`

The cookbook is part of the builder setup. When planning a new backend service, follow these standards first.

## Service Inventory First

Before planning a new backend service, protobuf package, or gRPC service, check:

```text
contracts-repo/docs/contract-inventory.json
services-repo/docs/grpc-service-inventory.json
```

Use the inventory to answer:

- Does this contract package, message, RPC, domain model, mapper, or security hook already exist?
- Does this service boundary already exist?
- Does an existing proto package already own this domain?
- Is the requested work a new RPC on an existing service instead of a new service?
- Which `KnownGRPCMethods`, `DefaultRolePermissions`, docs, tests, and admin hooks must be updated?

If a new contract, service, or RPC is added, update the inventories in the same change. The inventories are intentionally simple JSON so humans and builder agents can read them before generating code.

## Planning Noise Suppression

The builder must prefer existing owners over speculative skeletons.

Treat words like `integrate`, `wire`, `connect`, `upgrade`, `implement`, `expose`, `add`, `update`, `fix`, `support`, and `enable` as action verbs. Do not infer those words as domain names.

If contract/service inventories already contain a matching RPC or service boundary, do not propose a new proto package, new service process, new database table, or new CRUD repository skeleton. Instead, report:

- Existing owner and RPC/service boundary.
- Whether the request is backend implementation, app integration, AI tool integration, or documentation/inventory work.
- RBAC/public-method status and any permission gap.
- Caller compatibility impact.
- Docs, inventories, tests, and verification commands.

Only propose new backend skeletons when the user explicitly requests a new service/backend capability or no existing owner can be found.

## Core Rule

Frontend apps, admin apps, customer apps, and AI agents must not write directly to the OLTP database. They call backend service APIs. Backend services own:

- Protobuf/gRPC API behavior.
- Security and RBAC enforcement.
- Ownership checks.
- Database models and repositories.
- Migrations and seed data.
- Admin hooks for operational data.
- Structured logging.
- Tests for security, ownership, and persistence behavior.

## External Ingestion Standard

External crawlers, importers, and batch jobs must import platform data through authenticated service APIs, not direct SQL. The backend service that owns the domain owns validation, dedupe, upsert behavior, timestamps, RBAC, and repository persistence.

For recurring external data ingestion:

- Prefer a bulk RPC on the existing owning service over one call per record.
- Make imports idempotent using source/external identifiers and existing universal domain records.
- Require an authenticated operational role such as `agent`; do not make import RPCs public.
- Keep crawler/provider code separate from service client code.
- Return concise batch counts and per-record results so skipped records are visible.
- Keep SQL in the service repository layer, never in the crawler/importer.

## External Provider Submission Standard

External provider actions, such as ATS job application submission, must be split into discovery and submit steps on the existing owning service.

For provider-backed customer mutations:

- Add a read/discovery RPC that returns provider metadata, required fields, supported questions, and manual-application status without submitting.
- Add a separate submit RPC only when the platform can validate the authenticated customer, target record, selected resume/profile, and explicit confirmation.
- Require `confirmed=true` for submit RPCs that perform external side effects.
- Derive `customer_id` from the authenticated JWT by looking up `customers.user_id`; do not trust browser/model-supplied customer ids.
- Persist sanitized provider status and request/response summaries for audit, but do not store raw provider payloads, resume binary data, tokens, or secrets.
- Return manual/failure status when provider fields are unsupported instead of guessing answers or weakening validation.
- Expose AI submit tools only behind a prompt rule that first calls discovery, collects required answers, summarizes the target job/resume/profile, and asks for explicit confirmation.

## Metrics Read Model Standard

Dashboards and KPI surfaces must use service-owned read APIs instead of app-side or crawler-side direct database count queries.

For market-wide or cross-tenant metrics:

- Put the metric contract on the existing domain service that owns the source data.
- Store bounded read-model snapshots when the metric would otherwise require broad counts or grouping on every page load.
- Refresh snapshots from domain write/import paths when practical, and refresh lazily only when no snapshot exists.
- Keep chart buckets bounded and serializable so app payloads stay small.
- Keep customer-specific metrics scoped by authenticated identity in the service; do not let callers provide arbitrary customer ids for self-service metrics.
- Treat metrics RPCs as protected methods and update `KnownGRPCMethods`, `DefaultRolePermissions`, docs, inventories, and tests in the same change.

## Service Shape

New services should follow this shape unless the repo already has a more specific local pattern:

```text
new-service/
  main.go
  logging.go
  rbac.go
  admin_http.go          optional, only when service owns admin operations
  seed.go                optional, only when seed data is required
  internal/
    models/
      models.go
  domain-area/
    handler.go
    repository.go
    handler_test.go
  docs/
    architecture.md
    api.md
    grpc-security.md
    logging.md
    api-testing.md
```

For a new module inside an existing service, use the current user-service package pattern:

```text
feature/
  handler.go
  repository.go
  handler_test.go
```

Handlers implement generated gRPC server interfaces. Repositories own persistence. Keep authorization decisions close to handlers and durable ownership guarantees close to repositories.

## Contract-First Standard

Every new business API starts in `contracts-repo/packages/ceerat-contracts`.

Required steps:

1. Add or update the `.proto` file.
2. Generate protobuf and gRPC code through the repository's normal generation flow.
3. Add protected full gRPC method names to `KnownGRPCMethods`.
4. Add default permissions to `DefaultRolePermissions`.
5. Add intentionally public methods to `DefaultPublicMethods` only when truly needed.
6. Update service handlers to implement generated interfaces.
7. Update docs and tests.

Full method names must use this exact format:

```text
/package.Service/Method
```

Examples:

```text
/customer.CustomerService/ListCustomers
/service.ServiceManager/ListServices
/order.OrderManager/CreateOrder
/invoice.InvoiceManager/CreateInvoice
```

Default policy:

- `admin` usually gets `*`.
- `agent` gets internal operational methods needed for staff workflows.
- `customer` gets only self-service methods.
- Public methods should normally be limited to login, registration, token validation, and health checks.

Contracts must not depend on apps or service internals.

## Startup Standard

Service startup should be predictable and boring:

1. Create a structured JSON logger.
2. Load configuration from environment variables.
3. Connect to PostgreSQL.
4. Run migrations or explicit migration setup.
5. Seed required data idempotently.
6. Create repositories.
7. Create token validator or service-specific validators.
8. Load RBAC cache when the service owns RBAC data.
9. Build gRPC interceptors.
10. Register gRPC services.
11. Start admin HTTP API if the service owns admin operations.
12. Enable gRPC reflection for local inspection.
13. Serve.

Unary gRPC interceptor order:

```text
JWT -> RBAC -> Logging -> Handler
```

This order matters. JWT establishes identity, RBAC checks method permissions, logging records the final status and duration, and the handler applies business and ownership rules.

Stream gRPC requests should use JWT and RBAC before the handler when applicable.

## Configuration Standard

Minimum service configuration:

| Variable | Purpose |
| --- | --- |
| `PORT` | gRPC listen port. |
| `DB_HOST` | PostgreSQL host. |
| `DB_PORT` | PostgreSQL port. |
| `DB_USER` | PostgreSQL user. |
| `DB_PASSWORD` / `DB_PASS` | PostgreSQL password. |
| `DB_NAME` | PostgreSQL database name. |
| `JWT_SECRET` | JWT signing secret. |
| `JWT_AUTH_ENABLED` | Enables JWT/RBAC enforcement. |
| `CEERAT_ENV` / `APP_ENV` | Runtime environment label. |

Optional service variables:

| Variable | Purpose |
| --- | --- |
| `<SERVICE>_ADMIN_PORT` | Admin HTTP port. |
| `RBAC_CACHE_REFRESH_INTERVAL` | Periodic permission cache refresh. |
| `<SERVICE>_SEED_*` | Idempotent seed data configuration. |

Production rule: never rely on local default secrets outside local development.

## gRPC API Standard

Business APIs should be gRPC. Admin/operations APIs may be admin-only HTTP when browser admin tools need them.

Current service API areas in `ceerat-user-service`:

| Area | Proto package | Responsibility |
| --- | --- | --- |
| Auth | `proto/auth` | Users, login, registration, token validation, profile/password changes. |
| Customer | `proto/customer` | Customer profiles and customer ownership flows. |
| Service Manager | `proto/service` | Service catalog, product catalog, customer carts, and customer-service assignments. |
| Order Manager | `proto/order` | Orders, order status, order services, self-service orders. |
| Career | `proto/career` | Companies, jobs, skill profiles, resumes, job carts, and job applications. |
| AI Threads | `proto/ai` | Persisted sanitized AI chat thread history for agent and customer profiles. |

The service default gRPC address is:

```text
localhost:50051
```

Protected gRPC calls must include one of:

```text
authorization: Bearer <jwt>
x-auth-token: <jwt>
```

Error behavior should use canonical gRPC codes:

| Situation | Code |
| --- | --- |
| Missing/invalid token | `Unauthenticated` |
| Missing authenticated context | `Unauthenticated` |
| Role cannot call method | `PermissionDenied` |
| User cannot access record | `PermissionDenied` |
| Missing/invalid request fields | `InvalidArgument` |

Messages should be safe and generic, such as `authentication required`, `invalid token`, and `access denied`.

## AI Thread Service Standard

AI chat thread persistence is owned by `ceerat-user-service` through `ai.AIThreadService` in `contracts-repo/packages/ceerat-contracts/proto/ai/ai.proto`.

Current protected methods:

```text
ai.AIThreadService/GetOrCreateThread
ai.AIThreadService/GetThread
ai.AIThreadService/ListThreads
ai.AIThreadService/AppendMessage
ai.AIThreadService/ReplaceThreadMessages
ai.AIThreadService/DeleteThread
```

Thread records must be scoped by authenticated user id, profile, and external thread id. Treat the conceptual keys as:

```text
agent:<user_id>:<session_id>
customer:<user_id>:<session_id>
```

The service should enforce this scope from JWT context, not from browser-supplied ownership fields. Customer callers may only use `THREAD_PROFILE_CUSTOMER`; agent/admin callers may only use `THREAD_PROFILE_AGENT` unless a future explicit requirement changes profile access rules.

Persistence rules:

- Store only sanitized `user` and final `assistant` messages.
- Do not store system prompts.
- Do not store OpenAI tool-call protocol messages.
- Do not store raw tool results.
- Do not store JWTs, authorization headers, request metadata, or debug traces in thread content.
- Use repository-level ownership filters for every get/list/append/replace/delete operation.

App/agent integration rules:

- `ceerat-agent-service` loads history from `AIThreadService` before calling OpenAI.
- `ceerat-agent-service` appends the user message and final assistant response only after a completed turn.
- Browser apps expose thread list/history through same-origin proxy routes; browser assets must not call gRPC or the database directly.

## Admin HTTP Standard

Only add admin HTTP endpoints when the service owns operational data that admins must manage.

Current user-service admin API default:

```text
http://localhost:8081
```

Admin HTTP routes must:

1. Read token from `Authorization: Bearer <token>` or `X-Auth-Token`.
2. Validate token.
3. Load the current user from the database or identity source.
4. Require `role == "admin"`.
5. Apply the operation.
6. Refresh affected in-memory caches before returning success.
7. Return JSON with a clear status or an `error` field.

Admin HTTP should set basic security headers:

```text
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
```

Use admin HTTP for operational management, not ordinary customer, app, or agent workflows.

Current important admin areas:

- Current admin identity.
- User list/create/update/password reset/role change.
- Role list/create/update/delete.
- Role permission list/create/delete.
- Known gRPC method list.
- Manual RBAC cache refresh.

## Security Standard

Use shared hooks from `contracts-repo/packages/ceerat-contracts/security`.

| Hook | Purpose |
| --- | --- |
| `DefaultPublicMethods` | Exact gRPC methods that bypass JWT/RBAC. |
| `KnownGRPCMethods` | Methods assignable through admin/RBAC tooling. |
| `DefaultRolePermissions` | Seed permissions for default roles. |
| `NewJWTInterceptor` | Validates tokens and injects authenticated user context. |
| `NewRBACInterceptor` | Checks role permission for the current gRPC method. |
| `WithAuthenticatedUser` | Test/helper hook to attach user identity to context. |
| `AuthenticatedUserFromContext` | Handler hook to read authenticated user identity. |

Protected calls require a JWT in metadata:

```text
authorization: Bearer <jwt>
```

The alternate header is:

```text
x-auth-token: <jwt>
```

Token values must never be logged.
Auth validation responses should return sanitized current user claims from the auth service. Callers must not decode JWT payloads locally after `auth.Auth/ValidateToken`.

Current default public methods are intentionally small:

```text
/auth.Auth/Auth
/auth.Auth/Create
/auth.Auth/RegisterCustomer
/auth.Auth/Register
/auth.Auth/Login
/auth.Auth/ValidateToken
/grpc.health.v1.Health/Check
/health.Health/Check
```

`Register` and `Login` are compatibility names. Current generated auth methods use `/auth.Auth/Create`, `/auth.Auth/RegisterCustomer`, and `/auth.Auth/Auth`.

Handler pattern:

```go
authUser, ok := security.AuthenticatedUserFromContext(ctx)
if !ok {
    return nil, status.Error(codes.Unauthenticated, "authentication required")
}
```

Ownership pattern:

```go
if authUser.Role == "customer" && requestedUserID != "" && requestedUserID != authUser.ID {
    return nil, status.Error(codes.PermissionDenied, "access denied")
}
```

RBAC answers:

```text
Can this role call this method?
```

Handlers and repositories answer:

```text
Can this user access this record?
```

Customer-owned data must be scoped to the authenticated user. Examples:

- Customer users can only get/update their own user profile.
- Customer users cannot list all customers.
- Customer profile access is checked against `customers.user_id`.
- Customer cart access resolves the authenticated user to its own customer profile and denies another `customer_id`.
- Customer service assignments are filtered or denied if they belong to another customer.
- Order reads and writes are scoped by authenticated user id.
- Product catalog reads are visibility scoped: customer role can only read/list/add active products.

`JWT_AUTH_ENABLED=false`, `0`, or `no` disables JWT/RBAC and should only be used for local troubleshooting.

## RBAC Cache Standard

If the service owns RBAC data, use the existing `ceerat-user-service` pattern:

- Load role permissions from the database at startup.
- Store them in an in-memory map:

```text
role -> grpc_method -> allowed
```

- Support wildcard `*` for full access.
- Expose a manual refresh hook for admin use.
- Optionally refresh periodically with `RBAC_CACHE_REFRESH_INTERVAL`.

Admin endpoints that mutate roles or permissions must refresh the cache before returning success.

If a new service does not own RBAC data, do not create another RBAC database. Use the shared permission source or call the central owner. One source of truth is more important than local convenience.

## Persistence Standard

Model rules:

- Put GORM entities under `internal/models`.
- Add explicit indexes for lookup paths used by handlers.
- Use unique constraints for natural uniqueness, such as email or order number.
- Use foreign keys where ownership is stable.
- Use nullable foreign keys for optional either/or relationships. Example: a cart item may reference either a service row or a product row, so the unused FK must be `NULL`, not an empty string.
- Keep password/token fields out of response mapping.
- Snapshot mutable catalog data into historical records when needed.

Repository rules:

- Validate required IDs before querying.
- Scope customer-owned reads and writes by authenticated user id.
- Use transactions for multi-table writes.
- Recalculate totals inside the same transaction that adds, updates, removes, or clears line items.
- Keep protobuf mapping outside the repository where practical.
- Return errors handlers can map to gRPC-friendly statuses.

Ownership-safe query pattern:

```go
func (r *Repository) GetOrder(id string, userID string) (*domain.Order, error) {
    if strings.TrimSpace(id) == "" || strings.TrimSpace(userID) == "" {
        return nil, status.Error(codes.InvalidArgument, "order id and user id are required")
    }

    var order models.OrderEntity
    if err := r.db.Where("id = ? AND user_id = ?", id, userID).First(&order).Error; err != nil {
        return nil, err
    }

    return order.ToDomain(), nil
}
```

## Logging Standard

Use structured JSON logs through Go `log/slog`.

Stable service fields:

| Field | Meaning |
| --- | --- |
| `service` | Service name, for example `ceerat-user-service`. |
| `env` | Runtime environment from `CEERAT_ENV` or `APP_ENV`. |
| `time` | Log timestamp. |
| `level` | Log level. |
| `msg` | Event message. |

gRPC request log fields:

| Field | Meaning |
| --- | --- |
| `grpc_method` | Full gRPC method name. |
| `status` | gRPC status code. |
| `duration_ms` | Request duration in milliseconds. |
| `error` | Error string when the call fails. |

Every service should log:

- Startup and listen address.
- Database connection failures.
- Auth mode enabled/disabled.
- Admin or internal API startup.
- Seed/migration outcomes.
- Security/cache refresh failures.
- Important business events.

Recommended pattern:

```go
logger.Info("order created",
    "order_id", order.ID,
    "customer_id", order.CustomerID,
    "user_id", order.UserID,
    "total", order.Total,
)
```

Error pattern:

```go
logger.Error("order creation failed",
    "customer_id", customerID,
    "user_id", userID,
    "error", err,
)
```

In local/dev only, sanitized payload logging may include protobuf request/response bodies. Redact fields whose names include:

```text
password
token
secret
key
```

Never log:

- Plain text passwords.
- Raw JWTs.
- OpenAI/API keys.
- Database passwords.
- Full request headers.
- Large production payloads.
- Full customer PII unless local debugging specifically requires it.

When the platform is started through infra scripts, logs usually go to:

```text
logs/user-service.log
logs/postgres.log
logs/web-ui.log
logs/customer-ui.log
logs/admin-ui.log
logs/agent-service.log
```

Operational logs are not the reporting database. For business reporting, agent learning, executive summaries, recommendations, discounts, and product insights, use a separate BI/intelligence store fed by explicit events or copied data.

## API Testing Standard

Services should enable gRPC reflection for local inspection.

Useful commands:

```bash
grpcurl -plaintext localhost:50051 list
grpcurl -plaintext localhost:50051 list auth.Auth
grpcurl -plaintext localhost:50051 describe auth.Auth
grpcurl -plaintext localhost:50051 describe auth.User
```

Login and capture a token:

```bash
grpcurl -plaintext \
  -d '{"email":"admin@ceerat.local","password":"admin123"}' \
  localhost:50051 \
  auth.Auth/Auth
```

Call a protected method:

```bash
grpcurl -plaintext \
  -H "authorization: Bearer ${TOKEN}" \
  -d '{}' \
  localhost:50051 \
service.ServiceManager/ListServices
service.ServiceManager/ListProducts
```

Product catalog methods are owned by `service.ServiceManager`. Customer role can read/list active products only; admin and agent roles can create, update, and delete products.

Cart methods are owned by `service.ServiceManager`:

```text
service.ServiceManager/GetCart
service.ServiceManager/AddCartItem
service.ServiceManager/UpdateCartItem
service.ServiceManager/RemoveCartItem
service.ServiceManager/ClearCart
```

Cart smoke tests should cover:

- Customer can get its own cart without passing `customer_id`.
- Customer cannot pass another `customer_id`.
- Customer can add active product items and service items.
- Customer cannot add inactive products.
- Update, remove, and clear recalculate totals.
- `carts` and `cart_items` migrate successfully against PostgreSQL.

Career methods are owned by `proto/career` inside `ceerat-user-service`:

```text
career.CareerProfileService/CreateSkillProfile
career.CareerProfileService/ListMySkillProfiles
career.CareerProfileService/AddSkillToProfile
career.CareerProfileService/BatchAddSkillsToProfile
career.CareerProfileService/UpdateSkillInProfile
career.CareerProfileService/CreateResume
career.CareerProfileService/ParseResumeText
career.CareerProfileService/ImportResumeDraft
career.CareerProfileService/ListMyResumes
career.CareerProfileService/UpdateResume
career.CareerProfileService/DeleteResume
career.CareerProfileService/DownloadResume
career.CareerProfileService/CreateEmploymentRecord
career.CareerProfileService/BatchCreateEmploymentRecords
career.CareerProfileService/ListMyEmploymentRecords
career.CareerProfileService/GetEmploymentRecord
career.CareerProfileService/UpdateEmploymentRecord
career.CareerProfileService/ArchiveEmploymentRecord
career.CareerProfileService/AttachEmploymentRecordToResume
career.CareerProfileService/BatchAttachEmploymentRecordsToResume
career.CareerProfileService/DetachEmploymentRecordFromResume
career.CareerProfileService/UpdateResumeEmploymentRecord
career.CareerProfileService/ListResumeEmploymentRecords
career.CareerProfileService/GetMyCareerMetrics
career.JobService/CreateCompany
career.JobService/ListCompanies
career.JobService/GetCompany
career.JobService/UpdateCompany
career.JobService/CreateJob
career.JobService/GetJob
career.JobService/SearchJobs
career.JobService/UpdateJob
career.JobService/CloseJob
career.JobService/ReopenJob
career.JobService/ImportATSJobs
career.JobService/GetCareerMarketMetrics
career.JobCartService/GetJobCart
career.JobCartService/AddJobToCart
career.JobCartService/UpdateCartItemProfile
career.JobCartService/RemoveJobFromCart
career.JobCartService/ClearJobCart
career.JobApplicationService/ApplyToJob
career.JobApplicationService/ApplyToCartJobs
career.JobApplicationService/DiscoverJobApplication
career.JobApplicationService/SubmitJobApplication
career.JobApplicationService/ListMyApplications
career.JobApplicationService/GetMyApplication
career.JobApplicationService/ListApplications
career.JobApplicationService/GetApplication
career.JobApplicationService/UpdateApplicationStatus
```

Career ownership and security rules:

- Companies and jobs are global operational records for agent/admin workflows.
- Company create/update must run duplicate validation against existing global companies. Normalize case, punctuation, whitespace, common legal suffixes such as `Inc`, `LLC`, `Ltd`, `Corp`, and acronym punctuation before comparing. Reject exact or highly similar names with a clear validation error.
- ATS crawlers and importers must call `career.JobService/ImportATSJobs` with an authenticated agent token. They must not write companies/jobs directly to Postgres or Typesense. Imports are batch-oriented, idempotent by source/external ids, and should refresh read-optimized market metrics after successful job upserts.
- Job search is owned by `career.JobService/SearchJobs`. Browser apps, AI tools, crawlers, and admin/customer UIs must not call Typesense directly or receive the Typesense API key.
- Typesense-backed job search is an implementation detail of `ceerat-user-service`; Postgres remains the source of truth and database fallback must preserve open-job enforcement.
- Customer job searches must be forced to open jobs from authenticated JWT context. Do not trust browser-supplied status or customer ownership fields for customer search.
- Search request fields may include keyword, company name, company id, location, work mode, employment type, department, seniority, skills, country, source, sort, page size, and page token.
- Search responses may include total/page metadata and customer-friendly facet buckets for company, location, source, work mode, employment type, department, seniority, skills, and country. Hide negative boolean work-mode buckets such as `false` remote/hybrid/onsite values.
- Career market metrics are service-owned read models. Customer UI and AI tools should use `GetCareerMarketMetrics` and `GetMyCareerMetrics` instead of broad app-side count queries or inferring totals from paginated search responses.
- Customer-owned career records include skill profiles, profile skills, resumes, reusable employment records, resume employment attachments, job carts, and applications.
- Customer methods must derive customer identity from the authenticated JWT by looking up `customers.user_id`; do not trust customer-supplied `customer_id`.
- Resume text upload/import is a CareerProfile service-owned workflow. Clients may send text/markdown to `ParseResumeText`, then persist with `ImportResumeDraft` or focused batch CareerProfile RPCs. Apps, AI tools, crawlers, and browser code must not create profile skills, employment records, resume attachments, or resumes through direct database writes.
- Resume upload parsing must reject blank, oversized, or unsupported file types before persistence. Do not log raw uploaded resume text; keep extracted profile/resume content inside the intended customer-owned Career records.
- Employment records are reusable customer-owned work-history records, not skills and not embedded resume-only fields. Resumes attach them through join records that can carry sort order, include/exclude, tailored title, and tailored summary. Attach/detach/update flows must verify ownership of both the resume and the employment record.
- Resume create/list/update/delete/download are CareerProfile self-service capabilities. Fetch the resume by authenticated customer id and resume id before mutation or rendering PDF bytes; do not create a generic download service or trust a supplied customer id. Delete/archive behavior must handle dependent applications safely and should avoid losing historical application snapshots.
- Resume PDF export should include the resume/profile content, profile skills, and attached employment records in a readable full-page layout. Do not put raw pipe separators into export text.
- External ATS application submission is owned by `career.JobApplicationService`: discover provider requirements first, require explicit customer confirmation before submission, validate selected resume/profile ownership, never invent answers to required provider questions, and fall back with `manual_application_required` plus application URL when provider submission is unsupported.
- Agent/admin job and application review workflows use protected Career RPCs. Apps and AI tools must not write directly to the database.
- Company keyword search should support practical lookup fields such as name, website, description, industry, location, source, external ID, and source URL.

Career smoke tests should cover:

- Duplicate company validation for case-only, punctuation-only, legal-suffix, acronym, and near-spelling variants such as `iBM`, `I.B.M. LLC`, or `Microsft`.
- Customer ownership for skill profiles, profile skills, resumes, employment records, resume employment attachments, cart, and applications.
- Resume update/delete/download success, blank id rejection, unsupported format rejection, dependent application safety, and PDF byte/content-type response shape.
- Employment record attach/detach/update ownership checks for both resume and employment record, including per-resume sort/include/tailoring fields.
- Career market metrics refresh after import, safe global aggregate reads, and authenticated customer workflow metrics.
- ATS import idempotency by source/external ids, batch validation, customer rejection, and indexing/metrics failures not breaking successful database import.
- RBAC denial for customer attempts to create companies/jobs or review all applications.
- Agent/admin create/list/update company and create/search/update/close/reopen job.
- Job search filters for keyword, company, status, source, location, employment type, remote type, department, seniority, skills, country, facets, and pagination.
- External application discovery, explicit confirmation rejection, sanitized provider audit records, and manual fallback for unsupported Greenhouse requirements.
- Application list/update-status flows for agent/admin.
- AI tool permission behavior when Career tools are involved.

Alternative token header:

```bash
grpcurl -plaintext \
  -H "x-auth-token: ${TOKEN}" \
  -d '{}' \
  localhost:50051 \
  auth.Auth/GetAll
```

Admin HTTP testing:

```bash
curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  http://localhost:8081/api/admin/me
```

Useful failure tests:

- Missing token should return `Unauthenticated`.
- Invalid token should return `Unauthenticated`.
- Wrong role should return `PermissionDenied`.
- Customer reading another customer's record should return `PermissionDenied`.
- Bad request fields should return `InvalidArgument`.

## Required Tests

For every new service or module, add focused tests for:

- Public method behavior.
- Protected method behavior without token.
- RBAC denied behavior.
- RBAC allowed behavior.
- Customer/user ownership boundaries.
- Repository scoping by authenticated user id.
- Transactional writes.
- Password/token redaction or response cleanup.
- Admin-only endpoints, if added.
- Cache refresh behavior, if the service has an in-memory cache.

Useful test hook:

```go
ctx := security.WithAuthenticatedUser(context.Background(), &security.AuthenticatedUser{
    ID:   "user-1",
    Role: "customer",
})
```

## Documentation Required For Services

Every new service should include:

- `README.md` for local running and configuration.
- `docs/architecture.md` for the service/platform view.
- `docs/api.md` for gRPC and admin HTTP APIs.
- `docs/grpc-security.md` for JWT, RBAC, public methods, and ownership rules.
- `docs/logging.md` for structured log fields and redaction.
- `docs/api-testing.md` for `grpcurl`, `curl`, auth, RBAC, and failure tests.
- `docs/<service>-architecture.html` if a visual overview helps.

Keep docs focused. Architecture is the 50,000-foot view. API, security, logging, and testing docs own their respective implementation details.

## New Service Cookbook

When asked to create a new service, the builder should follow this recipe:

1. Identify the domain boundary and owning service.
2. Define contracts first in `contracts-repo`.
3. Add full protected gRPC methods to `KnownGRPCMethods`.
4. Add default role permissions to `DefaultRolePermissions`.
5. Keep public methods rare and explicit in `DefaultPublicMethods`.
6. Create handlers implementing generated gRPC interfaces.
7. Create repositories with authenticated ownership scoping.
8. Add migrations/models/indexes/constraints.
9. Add idempotent seed data if required.
10. Wire startup with logger, config, DB, seed, repositories, validators, RBAC, interceptors, gRPC registration, admin HTTP if needed, reflection, and serve.
11. Use interceptor order `JWT -> RBAC -> Logging -> Handler`.
12. Use structured `slog` logs and redact secrets.
13. Add admin HTTP only for admin-owned operational management.
14. Add tests for auth, RBAC, ownership, repositories, transactions, logging redaction, admin hooks, and cache refresh.
15. Add README and focused docs.

Codex prompt template:

```text
Create a new Ceerat backend service for <domain>.

Follow ceerat-platform-builder-agent/.ceerat-agent/service-standards.md.
Use gRPC for business APIs.
Use shared JWT/RBAC hooks from ceerat-contracts/security.
Add protected methods to KnownGRPCMethods and DefaultRolePermissions.
Keep public methods minimal.
Add handler ownership checks for customer-owned data.
Use structured slog logging with redaction.
Add focused tests for auth, RBAC, ownership, and repositories.
Add README and architecture/API/security/logging/testing docs.
```

Definition of done:

- Contracts compile.
- Service builds.
- gRPC methods are registered.
- Known methods and default role permissions are updated.
- JWT/RBAC interceptors are wired.
- Ownership checks exist for user-owned or customer-owned data.
- Repositories scope sensitive reads/writes correctly.
- Logs are structured and secrets are redacted.
- Admin hooks are protected by admin-only auth.
- Tests cover security and ownership boundaries.
- Docs explain API, security, interfaces, logging, operations, and testing.

## Builder Knowledge Update Gate

After a service change is implemented, do not immediately rewrite builder-agent standards from the plan. First complete validation:

1. Run contract/service tests and builds.
2. Run `ceerat-builder check drift --output json`.
3. Run `ceerat-builder check apps --output json` if app or AI surfaces changed.
4. Confirm inventories describe the implemented surface.
5. Ask for or receive human validation of the behavior.

Only then update `.ceerat-agent` docs when the change establishes a reusable platform rule, ownership boundary, security rule, or cookbook pattern.

Use `ceerat-builder docs <scope> --output json` to locate the relevant builder, service, inventory, and app documents.
