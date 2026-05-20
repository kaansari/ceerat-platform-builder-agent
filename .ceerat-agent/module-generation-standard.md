# Module Generation Standard

The builder agent produces implementation plans only. It should not claim to generate code or change repositories.

## Required Plan Content

Every module plan must cover:

- Module name and business purpose.
- Business objects, relationships, ownership, and statuses.
- Contract/protobuf changes.
- Backend service ownership and implementation areas.
- Database tables, indexes, constraints, seed data, and migration strategy.
- UI surfaces and workflows.
- Security, RBAC, public methods, and ownership checks.
- AI tools and tool safety.
- Logging and business events.
- Infra/startup/config changes.
- Tests.
- Risks, missing decisions, and open questions.

The current builder JSON schema is compact:

```text
module_name
business_objects
required_protos
required_services
required_database_migrations
required_ui_pages
required_rbac_permissions
required_ai_agent_tools
required_tests
risks_questions
```

Put logging, BI, infra, and ownership details into the closest matching field.

## Service Ownership Decision

Use `ceerat-user-service` when the module is tightly coupled to:

- Users.
- Customers.
- Service catalog.
- Customer-service assignments.
- Orders.
- RBAC/admin management.
- Patient records.

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

