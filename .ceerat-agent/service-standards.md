# Service Standards

This file gives the builder agent service-level rules for creating or modifying Ceerat backend services. It is based on the current `ceerat-user-service` docs, especially:

- `services-repo/services/ceerat-user-service/docs/architecture.md`
- `services-repo/services/ceerat-user-service/docs/api.md`
- `services-repo/services/ceerat-user-service/docs/grpc-security.md`
- `services-repo/services/ceerat-user-service/docs/logging.md`
- `services-repo/services/ceerat-user-service/docs/api-testing.md`
- `services-repo/services/ceerat-user-service/docs/new-service-cookbook.md`

The cookbook is part of the builder setup. When planning a new backend service, follow these standards first.

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
| Service Manager | `proto/service` | Service catalog and customer-service assignments. |
| Order Manager | `proto/order` | Orders, order status, order services, self-service orders. |
| Patient | `proto/patient` | Simple patient CRUD and compatibility placeholders. |

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
- Customer service assignments are filtered or denied if they belong to another customer.
- Order reads and writes are scoped by authenticated user id.

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
- Keep password/token fields out of response mapping.
- Snapshot mutable catalog data into historical records when needed.

Repository rules:

- Validate required IDs before querying.
- Scope customer-owned reads and writes by authenticated user id.
- Use transactions for multi-table writes.
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
```

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
