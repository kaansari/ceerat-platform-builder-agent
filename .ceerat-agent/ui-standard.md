# UI Standard

Ceerat UIs are work-oriented operational tools. Plans should favor clear, repeatable workflows over marketing-style screens.

## App Inventory First

Before planning a new app route, page, template, static asset, chat surface, or AI HTTP endpoint, check:

```text
apps-repo/docs/app-surface-inventory.json
```

Use the inventory to answer:

- Does this route or handler already exist?
- Does this app already have the needed template or static asset area?
- Is the requested chat behavior already owned by `ceerat-web-ui`, `ceerat-customer-ui`, or `ceerat-agent-service`?
- Should the work extend an existing app surface instead of creating a duplicate?

If a new app surface is added, update the inventory in the same change.

## App Integration Planning

For app integration requests, first classify whether the backend capability already exists. If an existing backend RPC or service owner is found, the plan should stay focused on app routes, same-origin proxies, AI tool profile impact, docs/inventory updates, and verification. Do not propose new backend proto packages, database tables, or service skeletons just because the request uses action words such as `integrate`, `wire`, `connect`, `upgrade`, `implement`, `support`, or `enable`.

## UI Surfaces

| UI | Purpose | Backend dependency |
| --- | --- | --- |
| Admin UI | Admin users, roles, permissions, RBAC cache, operational controls | User service admin HTTP API |
| Web UI | Authenticated operational app, dashboard, orders, agent Career pages, AI Agent panel, full-page `/chatgpt-client/` | User service gRPC, agent service HTTP |
| Customer UI | Customer registration, profile/orders, customer Career self-service, and customer AI chat workflows | User service gRPC, agent service HTTP |

Validated ownership:

- Career administration belongs in the agent-facing `ceerat-web-ui`, not in the admin/security UI.
- Customer Career self-service belongs in `ceerat-customer-ui`, not in admin UI or agent-facing `ceerat-web-ui`.
- Admin UI remains focused on users, roles, RBAC, security, cache refresh, and system operations.
- Agent Career pages use same-origin web endpoints under `/api/agent/career/*`; the web app forwards the session JWT to `career.JobService` and `career.JobApplicationService`.
- Customer Career pages use same-origin customer endpoints under `/api/customer/career/*`; the customer app forwards the session JWT to `career.CareerProfileService`, `career.JobService`, `career.JobCartService`, and `career.JobApplicationService`.
- `ceerat-web-ui` is an active-agent portal. Do not allow customer/admin sessions to use agent-only pages or agent chat routes.
- `ceerat-customer-ui` is an active-customer portal. Do not allow agent/admin sessions to use customer-only pages, customer career routes, or customer chat routes.
- Customer Career pages are:
  - `/customer/career`
  - `/customer/career/profiles`
  - `/customer/career/resumes`
  - `/customer/career/resumes/import`
  - `/customer/career/employment`
  - `/customer/career/jobs`
  - `/customer/career/cart`
  - `/customer/career/applications`
- The placeholder `/agent/career/imports` surface exists for future CSV/import/scraper work. Future import workers should create companies/jobs through backend APIs, not direct database writes.

Customer Career rules:

- Customers can manage their own skill profiles, profile skills, resumes, resume downloads, reusable employment records, job cart, and job applications.
- Career navigation should consistently show Overview, Skill Profiles, Resumes, Employment Records, Jobs, Job Cart, and Applications, with hierarchical breadcrumbs and a back action on every page.
- Customer Career entity pages should use separate routes for list/search, create, detail, and edit. Use `/customer/career/{entity}`, `/customer/career/{entity}/new`, `/customer/career/{entity}/{id}`, and `/customer/career/{entity}/{id}/edit` where practical.
- Resume detail pages should show attached employment records and actions to attach/order/include/tailor existing reusable employment records. Users should not need to retype employment history for each resume.
- Resume import belongs on a separate page at `/customer/career/resumes/import`. The browser may read text/markdown files locally, but must call same-origin customer UI endpoints for parsing and import. Users must review and explicitly confirm the parsed draft before creating profile, skills, employment records, and resume records.
- Resume view/download UI should include profile skills and attached employment records through same-origin routes. Do not display raw PDF bytes in chat or browser text.
- Customers can search and view open jobs.
- Customer job search/list pages must call same-origin Ceerat API wrappers such as `/api/jobs/search`; frontend code must not call Typesense or external ATS providers directly.
- Job search UI should keep keyword and location first, with mobile-friendly expandable filters for company, work mode, employment type, department, seniority, skills, country, source, and sort.
- Show customer-friendly facet labels and counts when available, such as `Databricks (784)` or `Remote (161)`. Do not expose implementation words like `Typesense` or raw search metadata in UI copy.
- Keep `/customer/career/jobs` as the search/list page and `/customer/career/jobs/{id}` as the separate detail page. Do not render the search/list page under the detail route.
- Customers cannot create companies, create jobs, review all applications, or update application status.
- Customer identity must be derived by backend Career services from the authenticated JWT and `customers.user_id`; UI requests must not send or trust arbitrary `customer_id` values.
- The browser must call only same-origin customer UI routes. The app server forwards the JWT to backend gRPC.
- Update `apps-repo/docs/app-surface-inventory.json` whenever customer Career routes, templates, static files, or API bridges change.

## Browser/API Boundary

Browser code should call same-origin app endpoints. App servers/proxies call backend services.

Preferred flow:

```text
Browser
  -> app HTTP endpoint
  -> backend gRPC/admin HTTP API
  -> service handler
  -> repository/database
```

Do not plan direct browser-to-gRPC calls.

## Session and Token Handling

The web UI stores the backend JWT in an HttpOnly cookie named `ceerat_session`. Browser JavaScript should not receive the raw JWT.

Plans must preserve:

- HttpOnly session cookies.
- Authenticated page redirects.
- Role/status checks at the app boundary for portal-specific apps.
- Server-side JWT forwarding to gRPC or agent service.
- Redaction of passwords, tokens, secrets, and keys in logs.

Validated portal session rules:

- Agent-facing `ceerat-web-ui` login/session must require `role == agent` and active status.
- Customer-facing `ceerat-customer-ui` login/session must require `role == customer` and active status.
- Backend services remain the security boundary, but app-level role checks prevent wrong-role sessions from reaching pages and AI chat surfaces where backend tools will correctly deny access.

## Workflow Checklist

For each UI workflow, include:

- User role.
- Page route.
- App-side API endpoint.
- Backend API called.
- Permissions required.
- Empty/loading/error states.
- Validation behavior.
- Success feedback.
- Tests needed.

## AI Chat UI

Supported web AI chat surfaces:

- Dashboard AI Agent panel using `POST /api/agent/chat`.
- Full-page chat UI at `GET /chatgpt-client/`, served from `apps/ceerat-web-ui/web/chatgpt-client`.
- Customer UI full-page chat at `GET /chatgpt-client/`, served from `apps/ceerat-customer-ui/web/chatgpt-client`.

Chat surfaces must forward through their owning app server to `ceerat-agent-service`; browser assets must not call OpenAI directly.

Full-page chat surfaces include persisted thread UX:

- A history sidebar on `/chatgpt-client/`.
- Load previous thread.
- Start new chat.
- Delete thread.

Both browser apps expose the same same-origin thread routes to the browser:

```text
GET    /api/agent/threads
GET    /api/agent/threads/{session_id}
DELETE /api/agent/threads/{session_id}
```

In `ceerat-web-ui`, those routes proxy to `ceerat-agent-service` agent thread endpoints:

```text
GET    /agent/threads
GET    /agent/threads/{session_id}
DELETE /agent/threads/{session_id}
```

In `ceerat-customer-ui`, those same browser route names proxy to customer thread endpoints:

```text
GET    /customer/threads
GET    /customer/threads/{session_id}
DELETE /customer/threads/{session_id}
```

Thread UX must use `session_id` / `threadId` returned by the agent service. Do not default new browser threads to the authenticated user id; if no session id is supplied, let `ceerat-agent-service` generate a new external thread id.

Validated customer chat route:

```text
ceerat-customer-ui /api/agent/chat
ceerat-customer-ui /api/chatgpt-client/get-prompt-result
  -> ceerat-agent-service /customer/chat
  -> customer-safe tools only
```

Customer pages that support chat should include a visible chat launcher. If `/chatgpt-client/` works directly but the icon is missing, update the owning template before changing the chat backend.

## Admin and Executive Intelligence UI

Future AI summaries and recommendations belong in admin/executive surfaces. They should be based on structured BI events and insights, not raw logs.

Plans should include review states such as new, reviewed, accepted, dismissed, and implemented when proposing AI insights.
