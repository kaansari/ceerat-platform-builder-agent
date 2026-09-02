# Ceerat Service Architecture Context

This file is loaded by the Ceerat Service Builder Agent. It gives the agent the platform context it needs when planning backend service capabilities, contracts, security, RBAC, and database objects.

Public MCP or LLM-facing integrations must also apply
`public-ai-integration-security-profile.md`.

## Builder Scope

This builder agent is intentionally services-only.

In scope:

- Protobuf/gRPC contracts.
- Shared contract domain DTOs and mappers.
- Backend service handlers.
- Repositories and database access.
- PostgreSQL OLTP tables, indexes, constraints, seed data, and migrations.
- JWT, RBAC, public method allowlists, admin-only hooks, and ownership checks.
- Admin/operations gRPC methods owned by backend services.
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
     | gRPC
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

External ChatGPT / Codex customer
     |
     | remote MCP + OAuth-delegated bearer token
     v
ceerat-agent-gateway
     |
     | private authenticated gRPC
     v
Backend services
```

## Major Components

| Component | Responsibility | Depends on |
| --- | --- | --- |
| `infra` | Local stack start/stop, env wiring, process logs, PIDs, database startup | Apps, services, database |
| `contracts-repo/packages/ceerat-contracts` | Protobuf contracts, generated clients/servers, domain DTOs, mappers, shared security hooks | No app/service/db dependency |
| `services-repo/services/ceerat-user-service` | Core OLTP service for auth, users, customers, service/product catalog, orders, career, calendar, AI threads, RBAC, and admin/operations gRPC | Contracts, PostgreSQL |
| PostgreSQL OLTP | Source of truth for transactional records | Owned by backend services |
| Future BI database | Business events, rollups, AI insights, executive recommendations | Receives copied/evented data |
| `apps-repo/ai/ceerat-agent-gateway` | Public remote MCP resource server, OAuth token validation, strict tool schemas, confirmations, structured errors, audit and private gRPC adaptation | Keycloak/OIDC, backend gRPC |

Existing app and AI callers are documented in inventories for compatibility checks, but this builder does not design those surfaces.

## Validated Public Agent Gateway Boundary

The Phase 1 public-agent interoperability milestone was validated on 2026-08-31
from Codex and ChatGPT developer mode. Treat the following as reusable platform
architecture rules when a service change is exposed to an external model:

- Publish a narrow vendor-neutral MCP tool, never arbitrary gRPC reflection or
  a generic RPC proxy.
- The LLM host performs OAuth authorization code + PKCE and stores the tokens.
  The model never receives passwords, MFA values, authorization codes, refresh
  tokens, client secrets or session cookies.
- OAuth obtains the access token; protected MCP requests still use
  `Authorization: Bearer <token>`.
- The gateway validates signature/JWKS, issuer, audience/resource, expiry,
  client, configured CEERAT identity claim and scopes before any gRPC call.
- Identity and ownership IDs come from the validated principal. External tool
  inputs must not accept `user_id`, `customer_id`, role or scopes for self-service
  operations.
- Public OAuth tokens are not general internal service credentials. Adapt them
  to an authenticated, narrow internal assertion or exchange and preserve
  service RBAC plus repository ownership checks.
- MCP input schemas must allow reserved protocol metadata such as
  `params._meta` while rejecting other unknown application fields.
- The gateway must enforce those closed schemas at runtime for public,
  protected, no-argument, and nested argument objects; tool metadata is not the
  enforcement boundary.
- Authentication-only tools require a fully validated bearer token but need no
  additional business scope. Their OAuth tool declaration uses an empty scope
  list rather than requiring `openid` to appear in the access token scope claim.
- Consequential operations use prepare/confirm/execute and advertise accurate
  read-only/destructive/idempotent annotations. Server enforcement remains
  authoritative.
- Return a stable structured result/error envelope with request ID and operation
  state. Keep detailed token-validation reasons in sanitized server logs, not
  model-visible responses.

The completed milestone exposes identity, low-risk customer profile and
connection tools only. Automatic Keycloak-registration-to-CEERAT provisioning,
durable shared gateway state, authorization-server revocation integration and
a gateway-specific internal assertion remain production requirements.

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
gRPC: localhost:50051
```

It owns:

- JWT auth and token validation.
- User accounts.
- Customer profiles with distinct profile, shipping, and billing addresses.
- Service catalog records.
- Product catalog records.
- Customer carts and cart items for services/products.
- Customer-service assignments.
- Orders, product/service lines, address snapshots, tax, shipping, coupons, and payment setup metadata.
- Career companies, jobs, skill profiles, resumes, job carts, job applications, and customer calendar events.
- AI chat thread history for agent and customer profiles.
- RBAC roles and gRPC method permissions.
- Admin/operations management through `admin.AdminService` gRPC methods.
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
calendar.CalendarService
ai.AIThreadService
admin.AdminService
```

Validated ownership rule:

- Product catalog and Cart capabilities belong to `service.ServiceManager` unless a future inventory shows a stronger owner.
- Cart is a customer-owned workflow over service/product catalog items. Customer callers are resolved to their own `customers.user_id` profile and cannot choose another `customer_id`.
- Checkout finalization, cart pricing quotes, order-level coupons, shipping methods, and tax rules belong to `order.OrderManager`. Catalog/item discounts remain owned by `service.ServiceManager`.
- Customer shipping and billing addresses belong to `customer.CustomerService`. `UpdateMyCustomerProfile` is customer-owned and must derive identity from JWT context.
- Shipping and billing addresses are explicit new-system state. Quote/order creation requires complete addresses; order creation snapshots both. Tax jurisdiction uses shipping only, and repricing uses the immutable order shipping snapshot.
- Order pricing is `subtotal - order discount + shipping + tax`. The backend is authoritative for catalog-effective subtotal, coupon eligibility, shipping eligibility, tax selection, cent rounding, and final total.
- Default shipping options are Free ($0), Standard ($5), Three day ($10), and Next day ($20). Default tax is 9 percent only when no configured state/country tax rule matches.
- Order coupon codes are `OrderPricingRule` records with `kind=discount` and a non-empty code. Coupon validation is case-insensitive and may enforce schedule, region, minimum subtotal, and priority.
- Do not add backward-compatibility fallbacks for missing addresses, missing order address snapshots, or stale shipping method IDs; reject invalid state.
- Admin/agent callers may inspect or manage carts only through protected service APIs and explicit customer context.
- Career capability belongs to `ceerat-user-service` under `proto/career`.
- Career company and job records are global operational data for agent/admin workflows, not per-agent-owned records. ATS crawlers import them through `career.JobService/ImportATSJobs`; crawlers must not write directly to Postgres or Typesense.
- Career company create/update paths must guard global data quality by rejecting likely duplicate company names after normalization and similarity checks.
- Customer career profile, profile skill, resume, employment record, job cart, metrics, and application methods must derive customer identity from the authenticated JWT by looking up `customers.user_id`. Customer callers must not be trusted to submit arbitrary `customer_id` values.
- Resume text upload/import belongs to `career.CareerProfileService`. Clients call `ParseResumeText` for text/markdown validation and draft extraction, then `ImportResumeDraft` or batch CareerProfile RPCs to persist profile skills, reusable employment records, resumes, and resume-employment attachments. AI tools and web apps must not write these records directly.
- Employment records are reusable customer-owned Career records. They are not skills and are not duplicated directly inside each resume; resumes attach them through join records with per-resume ordering/include/tailoring fields.
- Resume create/update/delete/download belongs to `career.CareerProfileService`, not a standalone document service. The backend must fetch the resume by authenticated `customer_id` plus resume id before mutation or PDF generation. Resume export should include profile skills and attached employment records.
- Agent-facing career administration belongs in `ceerat-web-ui`; admin UI remains focused on users, roles, RBAC, security, and system administration.
- Customer-facing Career self-service belongs in `ceerat-customer-ui`. It uses `/customer/career...` pages and `/api/customer/career...` same-origin API bridges that forward the customer's JWT to backend Career gRPC services.
- Career job search belongs behind `career.JobService/SearchJobs`. `ceerat-user-service` may use Typesense for indexed search and facets, but Typesense remains a service-owned implementation detail with Postgres as source of truth and database fallback. Customer UI and AI tools consume search through Ceerat API/gRPC boundaries only.
- Career market/customer metrics are service-owned read models exposed through Career RPCs. Apps and AI tools should not compute broad global counts from paginated job search or direct database access.
- External ATS application flows belong to `career.JobApplicationService`: discover provider requirements, require explicit customer confirmation, submit only supported forms server-side, and return manual fallback URLs when provider requirements cannot be safely automated.
- Career job applications are resume-driven at the customer surface. Job cart items and application submit requests should carry the selected resume, not a separate customer-selected skill profile. The service may persist `skill_profile_id` internally by deriving it from the resume's owning profile for historical consistency.
- Applying to all jobs in a job cart must clear the job cart only after every application succeeds. Partial failures must leave the cart intact so the customer can correct missing resumes or provider issues.
- Customer calendar events belong to `calendar.CalendarService` in `proto/calendar` and are implemented by `ceerat-user-service/calendars`. Calendar events are customer-owned, JWT-scoped records for interviews, follow-ups, deadlines, assessments, offers, and custom career reminders. Apps may prefill `job_id`, `job_title`, `company`, and related entity fields, but persistence and ownership checks remain service-owned.
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

## Kubernetes Deployment Option

Ceerat also supports a Kubernetes deployment path owned by `infra/k8s`. Builder plans may mention this as deployment/config impact when a backend service, app-facing API, database dependency, secret, or runtime port changes.

Current Kubernetes shape:

```text
infra/k8s/
  dockerfiles/
    apps-repo.Dockerfile       # one image for apps-repo app and agent binaries
    services-repo.Dockerfile   # one image for services-repo backend binaries
  base/
    namespaces.yaml
    shared-config.yaml
    ceerat-user-service/
    ceerat-agent-service/
    frontend-apps/
    postgres/
    typesense/
    ingress/
  overlays/
    dev/
    staging/
    prod/
```

Local helper commands:

```text
infra/k8s-start.sh
infra/k8s-start.sh --local
infra/k8s-status.sh
infra/k8s-stop.sh
make k8-build
make k8-deploy
make k8-render
make start-k8
make status-k8
make stop-k8
```

Deployment image rule:

- `ceerat-apps-repo` contains app and agent binaries from `apps-repo`, including `ceerat-web-ui`, `ceerat-admin-ui`, `ceerat-customer-ui`, and `ceerat-agent-service`.
- `ceerat-services-repo` contains backend service binaries from `services-repo`, currently `ceerat-user-service`.
- `atscrawler` is intentionally not part of the Kubernetes app image.
- PostgreSQL uses the official `postgres:16-alpine` image as an in-cluster StatefulSet.
- Typesense is optional derived search infrastructure. Postgres remains the source of truth.

Runtime boundaries:

- Browser-facing apps run in the `ceerat-frontend` namespace.
- Backend services run in the `ceerat-backend` namespace.
- Data services run in the `ceerat-data` namespace.
- Apps and agents still call backend APIs; they must not write directly to Postgres or Typesense.
- `ceerat-user-service` reaches Postgres through `ceerat-db-config` and `ceerat-db-credentials`.
- Kubernetes manifests are not driven by `infra/.env`; K8s config lives in ConfigMaps and Secrets under `infra/k8s/base`.

Local development:

- `./k8s-start.sh --local` starts local browser port-forwards after deployments are ready.
- UI services are ClusterIP services; local browser access should use port-forwarding.
- K8s Postgres is also ClusterIP; database tools should connect through a port-forward such as `kubectl -n ceerat-data port-forward svc/postgres 55434:5432`.
- Local visibility should use `k9s`, `infra/k8s-status.sh`, `infra/k8s-logs.sh`, `kubectl logs`, and `kubectl get events`.
- Do not treat ingress, public DNS, or HTTPS as the default local debugging path.

Production ingress:

- Browser-facing production traffic should enter through an ingress controller or cloud load balancer, then route to `ceerat-frontend` services.
- Production hostnames should be real DNS names, for example `app.ceerat.com`, `customer.ceerat.com`, and `admin.ceerat.com`.
- Production ingress must use HTTPS certificates managed by the platform's normal certificate process.
- The ingress class is environment-specific. Traefik is suitable for K3s/Traefik clusters; Nginx ingress is a common fallback; cloud-managed ingress may use a provider-specific class.
- Backend and data services should remain internal by default: `postgres`, `typesense`, `ceerat-user-service`, and `ceerat-agent-service` are not public ingress targets unless a later security-reviewed architecture explicitly requires it.

Builder guidance:

- Service changes that add ports, env vars, secrets, database dependencies, health checks, or new service processes must include Kubernetes manifest impact in `integration_impact`.
- App-facing route, hostname, TLS, or ingress-controller changes are production deployment impact and should be described separately from local port-forward testing.
- Prefer HTTP or TCP probes unless the service explicitly implements the Kubernetes gRPC health protocol.
- Do not propose direct SQL access from apps, agents, crawlers, or UI containers as a Kubernetes shortcut.
- Keep Kubernetes docs in `infra/README.md` aligned with any durable deployment behavior.

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
