# Ceerat Platform Architecture Context

This file is loaded by the Ceerat Platform Builder Agent. It gives the agent the platform context it needs when planning new modules.

## Workspace Shape

Ceerat is split across sibling repositories:

```text
infra/
apps-repo/
services-repo/
contracts-repo/
ceerat-platform-builder-agent/
```

Important Go modules:

```text
contracts-repo/packages/ceerat-contracts
services-repo/services/ceerat-user-service
apps-repo/ai/ceerat-agent-service
apps-repo/apps/ceerat-admin-ui
apps-repo/apps/ceerat-web-ui
apps-repo/apps/ceerat-customer-ui
```

Local cross-repo Go development should use a parent-level `go.work`. Missing workspace entries can make Go try to download local module paths instead of using sibling repositories.

## 50,000 Foot View

Ceerat is organized around one core rule: apps and AI agents do not write directly to the OLTP database. They call backend services. Backend services own persistence, migrations, business rules, security, RBAC, and logging.

```text
Users / Admins
     |
     v
Browser Apps
     |
     | HTTP
     v
App servers / proxies
     |
     | gRPC or admin HTTP
     v
Backend services
     |
     | GORM / SQL
     v
PostgreSQL OLTP database

AI agent service
     |
     | approved gRPC tool calls
     v
Backend services
```

## Major Components

| Component | Responsibility | Depends on |
| --- | --- | --- |
| `infra` | Local stack start/stop, env wiring, process logs, PIDs, database startup | Apps, services, database |
| `contracts-repo/packages/ceerat-contracts` | Protobuf contracts, generated clients/servers, domain DTOs, mappers, shared security hooks | No app/service/db dependency |
| `services-repo/services/ceerat-user-service` | Core OLTP service for auth, users, customers, service catalog, orders, patients, RBAC, admin HTTP | Contracts, PostgreSQL |
| `apps-repo/apps/ceerat-web-ui` | Authenticated web app, dashboard, orders, AI Agent panel, full-page `/chatgpt-client/` UI | User service, agent service |
| `apps-repo/apps/ceerat-customer-ui` | Customer-facing self-service and customer registration | User service |
| `apps-repo/apps/ceerat-admin-ui` | Admin users, roles, permissions, RBAC cache management | User service admin HTTP API |
| `apps-repo/ai/ceerat-agent-service` | HTTP AI service using OpenAI tool calling and platform gRPC APIs | User service, OpenAI API |
| PostgreSQL OLTP | Source of truth for transactional records | Owned by backend services |
| Future BI database | Business events, rollups, AI insights, executive recommendations | Receives copied/evented data |

## Dependency Rules

- Apps depend on backend APIs, not databases.
- Agents depend on backend APIs, not databases.
- Services depend on contracts.
- Contracts must not depend on apps, services, GORM, repositories, or persistence.
- Business intelligence should use a separate analytics database, not raw logs and not heavy OLTP queries.
- Analytics writes must not block primary transactional workflows.

## Core Service Boundary

`ceerat-user-service` is currently the core service. It exposes:

```text
gRPC:       localhost:50051
Admin HTTP: localhost:8081
```

It owns:

- JWT auth and token validation.
- User accounts.
- Customer profiles.
- Service catalog records.
- Customer-service assignments.
- Orders and order service lines.
- Patient records.
- RBAC roles and gRPC method permissions.
- Admin HTTP management API.
- GORM entities and migrations.
- Structured JSON logging.

Registered gRPC service areas:

```text
auth.Auth
customer.CustomerService
service.ServiceManager
order.OrderManager
patient.patient
```

## Contracts Boundary

`contracts-repo/packages/ceerat-contracts` contains:

```text
proto/auth/
proto/customer/
proto/order/
proto/patient/
proto/service/
domain/
mapper/
security/
```

Allowed in contracts:

- Protobuf request/response definitions.
- Generated clients/servers.
- Shared domain DTOs.
- Mapper helpers.
- Shared security interceptors and method lists.

Not allowed in contracts:

- GORM tags.
- Database models.
- Repository interfaces.
- Service implementation logic.
- App/UI behavior.

## AI Chat Boundary

The active AI service is `apps-repo/ai/ceerat-agent-service`.

Browser chat surfaces are served by `ceerat-web-ui`:

```text
Dashboard AI Agent panel -> POST /api/agent/chat
Full-page chat UI        -> GET /chatgpt-client/
```

Both surfaces forward authenticated requests to:

```text
ceerat-agent-service POST /agent/chat
```

The agent validates the Ceerat JWT, calls OpenAI with tool definitions, then executes approved gRPC calls against `ceerat-user-service`. It must not write directly to PostgreSQL.

The old standalone `apps-repo/ai/ceerat-chatgpt-client` redirect helper is not part of the active architecture.

## Infra and Logs

Infra scripts start the local platform and write logs under the workspace `logs/` directory.

Common logs:

```text
logs/user-service.log
logs/postgres.log
logs/web-ui.log
logs/customer-ui.log
logs/admin-ui.log
logs/agent-service.log
```

Plans that add a process must include ports, env vars, log files, PID behavior, and start/stop integration.

## BI and System Intelligence Direction

Do not build business intelligence on raw application logs. Logs are for debugging. Business intelligence should use structured events in a separate BI/analytics database.

Preferred future flow:

```text
Application action
  -> structured business event
  -> BI/analytics database
  -> rollup/summary
  -> AI insight generation
  -> admin/executive review
```

Module plans should identify business events when the module creates meaningful product behavior.

