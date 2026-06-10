# Ceerat Service Architecture Context

This file is loaded by the Ceerat Service Builder Agent. It gives the agent the platform context it needs when planning backend service capabilities, contracts, security, RBAC, and database objects.

## Builder Scope

This builder agent is intentionally services-only.

In scope:

- Protobuf/gRPC contracts.
- Shared contract domain DTOs and mappers.
- Backend service handlers.
- Repositories and database access.
- PostgreSQL OLTP tables, indexes, constraints, seed data, and migrations.
- JWT, RBAC, public method allowlists, admin-only hooks, and ownership checks.
- Admin HTTP endpoints owned by backend services.
- Structured logging, business events, and BI/event handoff.
- Infra/config/log impact for service processes.

Out of scope:

- Frontend pages.
- HTML templates.
- CSS and browser JavaScript.
- UX interaction design.
- AI chat UI design.
- OpenAI prompt/tool implementation, except when noting service/API compatibility impact.

The builder may mention existing apps, AI tools, or infra only as integration impact. It should not plan frontend implementation.

## Workspace Shape

Ceerat is split across sibling repositories:

```text
infra/
apps-repo/
services-repo/
contracts-repo/
ceerat-platform-builder-agent/
```

Important Go modules for service planning:

```text
contracts-repo/packages/ceerat-contracts
services-repo/services/ceerat-user-service
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
| `services-repo/services/ceerat-user-service` | Core OLTP service for auth, users, customers, service/product catalog, orders, career, RBAC, admin HTTP | Contracts, PostgreSQL |
| PostgreSQL OLTP | Source of truth for transactional records | Owned by backend services |
| Future BI database | Business events, rollups, AI insights, executive recommendations | Receives copied/evented data |

Existing app and AI callers are documented in inventories for compatibility checks, but this builder does not design those surfaces.

## Dependency Rules

- Apps depend on backend APIs, not databases.
- Agents depend on backend APIs, not databases.
- Services depend on contracts.
- Contracts must not depend on apps, services, GORM, repositories, or persistence.
- Business intelligence should use a separate analytics database, not raw logs and not heavy OLTP queries.
- Analytics writes must not block primary transactional workflows.
- Service plans may include caller compatibility impact, but frontend implementation belongs to a separate UI agent.

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
- Product catalog records.
- Customer carts and cart items for services/products.
- Customer-service assignments.
- Orders and order service lines.
- Career companies, jobs, skill profiles, resumes, job carts, and job applications.
- AI chat thread history for agent and customer profiles.
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
career.CareerProfileService
career.JobService
career.JobCartService
career.JobApplicationService
ai.AIThreadService
```

Validated ownership rule:

- Product catalog and Cart capabilities belong to `service.ServiceManager` unless a future inventory shows a stronger owner.
- Cart is a customer-owned workflow over service/product catalog items. Customer callers are resolved to their own `customers.user_id` profile and cannot choose another `customer_id`.
- Admin/agent callers may inspect or manage carts only through protected service APIs and explicit customer context.
- Career capability belongs to `ceerat-user-service` under `proto/career`.
- Career company and job records are global operational data for agent/admin workflows, not per-agent-owned records. ATS crawlers import them through `career.JobService/ImportATSJobs`; crawlers must not write directly to Postgres or Typesense.
- Career company create/update paths must guard global data quality by rejecting likely duplicate company names after normalization and similarity checks.
- Customer career profile, profile skill, resume, employment record, job cart, metrics, and application methods must derive customer identity from the authenticated JWT by looking up `customers.user_id`. Customer callers must not be trusted to submit arbitrary `customer_id` values.
- Employment records are reusable customer-owned Career records. They are not skills and are not duplicated directly inside each resume; resumes attach them through join records with per-resume ordering/include/tailoring fields.
- Resume create/update/delete/download belongs to `career.CareerProfileService`, not a standalone document service. The backend must fetch the resume by authenticated `customer_id` plus resume id before mutation or PDF generation. Resume export should include profile skills and attached employment records.
- Agent-facing career administration belongs in `ceerat-web-ui`; admin UI remains focused on users, roles, RBAC, security, and system administration.
- Customer-facing Career self-service belongs in `ceerat-customer-ui`. It uses `/customer/career...` pages and `/api/customer/career...` same-origin API bridges that forward the customer's JWT to backend Career gRPC services.
- Career job search belongs behind `career.JobService/SearchJobs`. `ceerat-user-service` may use Typesense for indexed search and facets, but Typesense remains a service-owned implementation detail with Postgres as source of truth and database fallback. Customer UI and AI tools consume search through Ceerat API/gRPC boundaries only.
- Career market/customer metrics are service-owned read models exposed through Career RPCs. Apps and AI tools should not compute broad global counts from paginated job search or direct database access.
- External ATS application flows belong to `career.JobApplicationService`: discover provider requirements, require explicit customer confirmation, submit only supported forms server-side, and return manual fallback URLs when provider requirements cannot be safely automated.
- AI career tools execute through `ceerat-agent-service` platform gRPC clients. They must resolve company/job/application IDs using list/get/search tools and must not invent IDs. The agent may answer first-party account questions from sanitized `ValidateToken.user` session context.
- AI chat thread history belongs to `ceerat-user-service` under `proto/ai` as `ai.AIThreadService`.
- Agent and customer chat histories are scoped by authenticated user id, profile, and external thread id: `agent:<user_id>:<session_id>` and `customer:<user_id>:<session_id>` conceptually, with the backend enforcing JWT ownership.
- Persisted AI history must contain sanitized user and final assistant messages only. Do not persist system prompts, raw tool results, tool call protocol messages, authorization data, or model/tool debug payloads.
- Browser chat history UX belongs in the existing `ceerat-web-ui` and `ceerat-customer-ui` full-page `/chatgpt-client/` surfaces, not in the admin UI or a new standalone app.

## Contracts Boundary

`contracts-repo/packages/ceerat-contracts` contains:

```text
proto/auth/
proto/customer/
proto/order/
proto/career/
proto/ai/
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

## Caller Compatibility Boundary

The service builder should be aware that existing apps and AI tools call service APIs. Use these inventories for compatibility checks only:

```text
apps-repo/docs/app-surface-inventory.json
services-repo/docs/grpc-service-inventory.json
contracts-repo/docs/contract-inventory.json
```

When a service/API change affects callers, put that in `integration_impact`. Do not design frontend pages, app handlers, templates, JavaScript, AI prompts, or AI tools.

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
