# Module Generation Standard

The service builder agent produces backend service implementation plans only. It should not claim to generate code or change repositories.

## Required Plan Content

Every services-only module plan must cover:

- Module name and business purpose.
- Business objects, relationships, ownership, and statuses.
- Contract/protobuf changes.
- Backend service ownership and implementation areas.
- Database tables, indexes, constraints, seed data, and migration strategy.
- Security, RBAC, public methods, and ownership checks.
- Logging and business events.
- Infra/startup/config changes for backend services.
- Integration impact for existing apps, AI tools, or callers without designing frontend or AI UI.
- Tests.
- Risks, missing decisions, and open questions.

The current builder JSON schema is compact:

```text
module_name
business_objects
required_protos
required_services
required_database_migrations
required_rbac_permissions
required_logging_events
integration_impact
required_tests
risks_questions
```

Put service-owned admin HTTP hooks in `required_services`, database behavior in `required_database_migrations`, security behavior in `required_rbac_permissions`, logs/events in `required_logging_events`, and caller coordination in `integration_impact`.

Do not include frontend implementation details in any field.

## Inventory-First Recipe

Before proposing new contracts, services, or database objects, check:

```text
contracts-repo/docs/contract-inventory.json
services-repo/docs/grpc-service-inventory.json
```

For caller compatibility only, check:

```text
apps-repo/docs/app-surface-inventory.json
```

Use app/AI inventory only to identify follow-up integration impact. Do not plan UI pages, templates, CSS, browser JavaScript, or AI chat UI.

## Service Ownership Decision

Use `ceerat-user-service` when the module is tightly coupled to:

- Users.
- Customers.
- Service catalog.
- Product catalog.
- Customer-service assignments.
- Orders.
- Career companies, jobs, skill profiles, resumes, job carts, and job applications.
- RBAC/admin management.

Propose a new backend service only when the domain has clear independent ownership, separate scaling/security needs, or its own persistence lifecycle.

If proposing a new service, include:

- Repo/module path.
- gRPC port.
- Admin/internal HTTP port, if any.
- Database ownership.
- Startup and log integration.
- Contract changes.
- Security/RBAC wiring.
- Tests and docs.

## Contract-First Recipe

For backend APIs:

1. Add or update `.proto` definitions in `contracts-repo/packages/ceerat-contracts/proto/<module>`.
2. Add request/response messages.
3. Add gRPC service RPCs.
4. Add/update domain DTOs if needed.
5. Add mapper helpers if needed.
6. Regenerate protobuf code with `make proto`.
7. Add full gRPC method names to `security.KnownGRPCMethods`.
8. Add role defaults to `security.DefaultRolePermissions`.
9. Add public methods to `security.DefaultPublicMethods` only when necessary.

Full gRPC method format:

```text
/package.Service/Method
```

Current ownership example:

```text
/service.ServiceManager/CreateProduct
/service.ServiceManager/GetProduct
/service.ServiceManager/ListProducts
/service.ServiceManager/UpdateProduct
/service.ServiceManager/DeleteProduct
/service.ServiceManager/GetCart
/service.ServiceManager/AddCartItem
/service.ServiceManager/UpdateCartItem
/service.ServiceManager/RemoveCartItem
/service.ServiceManager/ClearCart
```

Product belongs to the current service catalog boundary. Prefer extending `service.ServiceManager` for product catalog behavior unless the inventory or requirements show a stronger owner.

Cart is also validated as part of the current `service.ServiceManager` boundary because it is a customer-owned workflow over service catalog and product catalog items. Prefer extending this service for cart-style service/product selection behavior unless the inventory shows a new checkout/order owner.

Career is validated as a `proto/career` module inside `ceerat-user-service`, not a standalone service. It owns:

```text
/career.CareerProfileService/*
/career.JobService/*
/career.JobCartService/*
/career.JobApplicationService/*
```

Use this ownership when requirements involve companies, jobs, skill profiles, resumes, job carts, or job applications unless the inventories show a newer owner.

Career caller coordination rules:

- Agent-facing career administration belongs in `ceerat-web-ui`.
- Admin UI should not become the career operations workspace; keep it focused on user/security/RBAC/system administration.
- AI career tools belong in `apps-repo/ai/ceerat-agent-service` and must call backend Career RPCs through the platform gRPC client.
- Company/job/application natural-language requests must resolve real IDs through list/get/search tools before mutation.

## Backend Service Recipe

For a module inside an existing service:

```text
feature/
  handler.go
  repository.go
  handler_test.go
```

For a new service:

```text
new-service/
  main.go
  logging.go
  rbac.go
  admin_http.go          optional
  seed.go                optional
  internal/models/
  feature/
    handler.go
    repository.go
    handler_test.go
```

Startup pattern:

1. Create structured JSON logger.
2. Load env config.
3. Connect to PostgreSQL.
4. Run migrations or migration setup.
5. Seed required data idempotently.
6. Create repositories.
7. Create token validator or service-specific validators.
8. Load RBAC cache or connect to RBAC owner.
9. Build gRPC interceptors.
10. Register gRPC services.
11. Start admin HTTP API if owned.
12. Enable gRPC reflection.
13. Serve.

Unary interceptor order:

```text
JWT -> RBAC -> Logging -> Handler
```

## Persistence Recipe

Plans must describe:

- Tables/entities.
- Primary keys.
- Foreign keys.
- Unique constraints.
- Indexes.
- Status values.
- Seed data.
- Transactions.
- Whether data belongs in OLTP or BI.

Repository rules:

- Validate required IDs.
- Scope customer-owned reads/writes by authenticated user id.
- Use transactions for multi-table writes.
- Snapshot mutable catalog data into historical records when needed.
- Apply visibility rules for catalog data, such as customer role seeing active products only.
- For either/or relationships, such as a cart item referencing either a service or a product, use nullable foreign keys for the optional side. Do not store empty strings in unused FK columns.
- Recalculate cart/order totals inside the same transaction that changes line items.
- Do not return password/token fields.
- Do not let apps or agents bypass service APIs.

## Documentation Recipe

For a new service or major module, plan updates to:

- README.
- API docs.
- API testing guide.
- gRPC security docs.
- Logging docs.
- Architecture docs if dependencies change.
- New service cookbook if a new pattern is introduced.

Do not plan frontend documentation from this agent unless the only need is to note caller compatibility impact.

## Post-Validation Builder Knowledge Update

The builder-agent should update its own durable documents only after implementation is validated.

Required order:

1. Implement the contract/service/database/security change.
2. Run the relevant tests and build commands.
3. Run builder checks such as `ceerat-builder check drift --output json` and `ceerat-builder check apps --output json` when app surfaces are involved.
4. Get human validation that the behavior and ownership are correct.
5. Update service docs and inventories to match the final implementation.
6. Update `.ceerat-agent` standards only when the change teaches the builder a reusable platform rule or ownership decision.

Use this helper to locate docs:

```bash
ceerat-builder docs all --output json
ceerat-builder docs builder --output json
ceerat-builder docs service --output json
ceerat-builder docs inventory --output json
ceerat-builder docs apps --output json
```

Do not update builder standards from a speculative plan. The standards are memory for validated platform behavior, not a scratchpad for ideas.
