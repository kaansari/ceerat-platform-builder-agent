# AI Tool Standard

This file gives the builder agent rules for planning Ceerat AI tools and future intelligence features.

## Current Agent Boundary

`apps-repo/ai/ceerat-agent-service` is the active HTTP AI agent service. It validates a Ceerat JWT, calls OpenAI, and executes approved platform operations through backend service APIs.

Current endpoints:

```text
POST /agent/chat
POST /customer/chat
GET  /agent/threads
GET  /agent/threads/{session_id}
DELETE /agent/threads/{session_id}
GET  /customer/threads
GET  /customer/threads/{session_id}
DELETE /customer/threads/{session_id}
```

Browser traffic reaches it through `ceerat-web-ui`:

```text
POST /api/agent/chat
POST /api/chatgpt-client/get-prompt-result
```

Customer browser traffic reaches the customer assistant through `ceerat-customer-ui`:

```text
POST /api/agent/chat
POST /api/chatgpt-client/get-prompt-result
```

Those customer UI routes forward to:

```text
POST /customer/chat
```

Current agent/admin tools on `POST /agent/chat`:

```text
create_customer
list_customers
list_services
assign_service_to_customer
create_order
list_orders
get_order
update_order_status
add_service_to_order
remove_service_from_order
create_company
list_companies
get_company
update_company
create_job
search_jobs
get_job
close_job
list_applications_for_job
update_application_status
```

Current customer-safe tools on `POST /customer/chat`:

```text
get_my_customer_profile
update_my_customer_profile
list_my_skill_profiles
create_skill_profile
add_skill_to_profile
list_my_resumes
create_resume
search_jobs
get_job
get_job_cart
add_job_to_cart
update_job_cart_item
remove_job_from_cart
clear_job_cart
apply_to_job
apply_to_cart_jobs
list_my_applications
get_my_application
```

The agent-facing browser UI remains in:

```text
apps-repo/apps/ceerat-web-ui/web/chatgpt-client
```

It is served by `ceerat-web-ui` at:

```text
http://localhost:3000/chatgpt-client/
```

The customer-facing browser UI remains in:

```text
apps-repo/apps/ceerat-customer-ui/web/chatgpt-client
```

It is served by `ceerat-customer-ui` at:

```text
http://localhost:3005/chatgpt-client/
```

Do not remove this UI when cleaning old AI modules. The old standalone redirect helper, if present, is different:

```text
apps-repo/ai/ceerat-chatgpt-client
```

That helper is not the active chat backend and should not be treated as the source of truth for AI chat.

## Active AI Request Flow

The expected runtime flow is:

```text
Browser chat UI
  -> owning app same-origin route
  -> ceerat-agent-service POST /agent/chat or POST /customer/chat
  -> ai.AIThreadService loads sanitized history by profile + session_id
  -> OpenAI chat completion with tool definitions
  -> ToolRunner executes requested tool calls
  -> platform.Client sends gRPC with authorization metadata
  -> ceerat-user-service validates JWT/RBAC/ownership
  -> PostgreSQL through the service repository layer
  -> ai.AIThreadService stores only user + final assistant messages
```

The browser must not call OpenAI directly. The browser must not call gRPC directly. The agent service must not write directly to PostgreSQL. Chat history persistence must go through `ai.AIThreadService`.

## Active AI HTTP Routes

`ceerat-agent-service` exposes:

```text
GET  /healthz
POST /agent/chat
POST /customer/chat
GET  /agent/threads
GET  /agent/threads/{session_id}
DELETE /agent/threads/{session_id}
GET  /customer/threads
GET  /customer/threads/{session_id}
DELETE /customer/threads/{session_id}
```

`POST /agent/chat` and `POST /customer/chat` require:

```http
Authorization: Bearer <ceerat-jwt>
Content-Type: application/json
```

Request shape:

```json
{
  "message": "List my customers",
  "session_id": "optional-conversation-id"
}
```

Response shape:

```json
{
  "reply": "Here are your customers...",
  "actions": ["list_customers"],
  "session_id": "thread-...",
  "threadId": "thread-..."
}
```

The agent service validates the bearer token before invoking the model. Invalid, missing, or malformed tokens must return an HTTP auth error before any tool execution.

`POST /agent/chat` must use the agent/admin operations system prompt and `ToolRunner.Run`.

`POST /customer/chat` must use the customer self-service system prompt and `ToolRunner.RunCustomer`.

Thread route rules:

- `/agent/threads...` uses `THREAD_PROFILE_AGENT`.
- `/customer/threads...` uses `THREAD_PROFILE_CUSTOMER`.
- Thread routes require `Authorization: Bearer <ceerat-jwt>`.
- List/get/delete routes must forward through `platform.Client` to `ai.AIThreadService`.
- Returned thread JSON may expose `threadId` as the external thread id for browser compatibility.
- If `POST /agent/chat` or `POST /customer/chat` receives no `session_id`, `ceerat-agent-service` should generate a new external thread id and return it in the chat response.

Persisted history rules:

- Load only sanitized previous `user` and final `assistant` messages before model completion.
- Append only the current user message and final assistant response after a completed turn.
- Do not persist system prompts.
- Do not persist OpenAI tool-call protocol messages.
- Do not persist raw tool results.
- Do not persist authorization headers, JWTs, or request metadata.

## Web UI AI Routes

`ceerat-web-ui` owns browser-facing AI routes:

```text
GET  /chatgpt-client
GET  /chatgpt-client/
GET  /chatgpt-client/assets/...
POST /api/agent/chat
GET  /api/agent/threads
GET  /api/agent/threads/{session_id}
DELETE /api/agent/threads/{session_id}
POST /api/chatgpt-client/get-prompt-result
```

Rules:

- `GET /chatgpt-client` redirects to `/chatgpt-client/`.
- `GET /chatgpt-client/` serves the full-page chat UI.
- `POST /api/agent/chat` forwards dashboard chat JSON to `ceerat-agent-service`.
- `GET /api/agent/threads`, `GET /api/agent/threads/{session_id}`, and `DELETE /api/agent/threads/{session_id}` proxy to `ceerat-agent-service` agent thread endpoints.
- `POST /api/chatgpt-client/get-prompt-result` adapts the full-page chat UI prompt shape to the active agent API and returns the plain-text reply expected by that UI.
- The web UI stores the backend JWT in the HttpOnly `ceerat_session` cookie and forwards it to the agent service as `Authorization: Bearer <jwt>`.

The important web UI environment variable is:

```text
CEERAT_AGENT_BASE_URL=http://localhost:8088
```

The web UI forwards both chat surfaces to:

```text
${CEERAT_AGENT_BASE_URL}/agent/chat
```

## Customer UI AI Routes

`ceerat-customer-ui` owns customer browser-facing AI routes:

```text
GET  /chatgpt-client
GET  /chatgpt-client/
GET  /chatgpt-client/assets/...
POST /api/agent/chat
GET  /api/agent/threads
GET  /api/agent/threads/{session_id}
DELETE /api/agent/threads/{session_id}
POST /api/chatgpt-client/get-prompt-result
```

Rules:

- Customer UI routes forward to `${CEERAT_AGENT_BASE_URL}/customer/chat`.
- Customer UI thread routes keep the browser path `/api/agent/threads...` for shared chat assets, but proxy to `${CEERAT_AGENT_BASE_URL}/customer/threads...`.
- Customer UI stores the backend JWT in the HttpOnly `ceerat_session` cookie and forwards it to the agent service as `Authorization: Bearer <jwt>`.
- Customer UI must accept only active `customer` sessions. Agent or admin users must not be allowed to keep a customer portal session, because customer-safe AI tools require customer ownership context and will correctly fail for non-customer roles.
- Customer chat must expose only customer self-service tools.
- Customer chat must not expose company/job administration, application review, all-customer listing, or agent/admin operations.
- The customer portal home/profile page and other customer pages should expose the same chat launcher when customer chat is supported. If the full-page chat URL works but the icon is missing, check the owning template before changing AI service behavior.

## Existing Tool Implementation Files

Future tool work must start from these files:

```text
apps-repo/ai/ceerat-agent-service/internal/agent/tools.go
apps-repo/ai/ceerat-agent-service/internal/platform/client.go
apps-repo/ai/ceerat-agent-service/internal/httpapi/server.go
contracts-repo/packages/ceerat-contracts/proto/...
contracts-repo/packages/ceerat-contracts/proto/ai/ai.proto
services-repo/services/ceerat-user-service/aithreads/
services-repo/services/ceerat-user-service/internal/security/...
```

Responsibilities:

- `internal/agent/tools.go` defines the OpenAI tool schemas and maps tool calls to platform client methods.
- `ToolRunner.Run` parses JSON tool arguments, attaches the session token to context, calls the platform client, and returns JSON string results to the OpenAI tool loop.
- `ToolRunner.RunCustomer` does the same for customer-safe tools only.
- `internal/platform/client.go` owns all gRPC clients and the JWT forwarding behavior.
- `internal/platform/client.go` includes the `ai.AIThreadService` client and typed methods for get/list/append/delete thread operations.
- `internal/httpapi/server.go` owns `/agent/chat`, `/customer/chat`, thread HTTP routes, bearer token validation, request validation, timeout handling, and response shaping.
- `services-repo/services/ceerat-user-service/aithreads` owns AI thread handler/repository behavior and profile/user scoping.
- contracts in `ceerat-contracts` define the protobuf request/response APIs.
- user-service security hooks define the final RBAC and ownership enforcement.

## Existing Tool Catalog Details

The current tools are intentionally small. Preserve their names unless there is a migration plan for prompts, docs, and UI assumptions.

| Tool | Type | Purpose | Backend gRPC call |
| --- | --- | --- | --- |
| `create_customer` | Mutation | Create a customer assigned to the authenticated user. | `customer.CustomerService/CreateCustomer` |
| `list_customers` | Read | List customers for the authenticated user. | `customer.CustomerService/ListCustomers` |
| `list_services` | Read | List available services, optionally by category/type. | `service.ServiceManager/ListServices` |
| `assign_service_to_customer` | Mutation | Assign an existing service to an existing customer. | `service.ServiceManager/AssignServiceToCustomer` |
| `create_order` | Mutation | Create an order for an existing customer with one or more existing services. | `order.OrderManager/CreateOrder` |
| `list_orders` | Read | List orders for the authenticated user, optionally by customer/status. | `order.OrderManager/ListOrders` |
| `get_order` | Read | Get one order by ID. | `order.OrderManager/GetOrder` |
| `update_order_status` | Mutation | Update an order status. | `order.OrderManager/UpdateOrderStatus` |
| `add_service_to_order` | Mutation | Add an existing service line to an existing order. | `order.OrderManager/AddServiceToOrder` |
| `remove_service_from_order` | Mutation | Remove a service line from an order. | `order.OrderManager/RemoveServiceFromOrder` |
| `get_current_user` | Read | Return the sanitized authenticated session user. | `auth.Auth/ValidateToken` |
| `create_company` | Mutation | Create a global career company. | `career.JobService/CreateCompany` |
| `list_companies` | Read | List or keyword-search global career companies. | `career.JobService/ListCompanies` |
| `get_company` | Read | Get one career company by ID. | `career.JobService/GetCompany` |
| `update_company` | Mutation | Update a global career company. | `career.JobService/UpdateCompany` |
| `create_job` | Mutation | Create a global career job for an existing company. | `career.JobService/CreateJob` |
| `search_jobs` | Read | Search global career jobs. | `career.JobService/SearchJobs` |
| `get_job` | Read | Get one career job by ID. | `career.JobService/GetJob` |
| `close_job` | Mutation | Close a career job. | `career.JobService/CloseJob` |
| `list_applications_for_job` | Read | List applications submitted to a job. | `career.JobApplicationService/ListApplications` |
| `update_application_status` | Mutation | Update a job application status. | `career.JobApplicationService/UpdateApplicationStatus` |

Current input behavior:

- `create_customer` requires `first_name` and `last_name`; address, email, and phone are optional.
- `list_customers` takes no arguments.
- `list_services` accepts optional `category` and `type`.
- Product catalog RPCs exist under `service.ServiceManager`, but there is not currently a product-specific AI tool. If one is added later, customer-facing reads must only expose active products and mutations must remain admin/agent-only.
- `assign_service_to_customer` requires `customer_id` and `service_id`; `status` defaults to `ordered`; empty or `today` `ordered_at` becomes the current local date.
- `create_order` requires `customer_id` and `services`; service items require `service_id` and may include quantity, agent name, schedule/start/due dates.
- `list_orders` accepts optional `customer_id` and `status`.
- `get_order` requires `order_id`.
- `update_order_status` requires `order_id` and `status`.
- `add_service_to_order` requires `order_id` and `service_id`; service details may include quantity, agent name, schedule/start/due dates.
- `remove_service_from_order` requires `order_id` and `order_service_id`.
- `get_current_user` takes no arguments and returns sanitized session user fields only.
- `create_company` requires `name`; website, industry, description, location, source, source URL, and external ID are optional. Backend duplicate validation rejects exact or highly similar global company names.
- `list_companies` accepts optional `keyword` and `source`. Company keyword search should cover practical lookup fields such as name, website, description, industry, location, source, external ID, and source URL. For "all companies", do not pass generic keywords such as `all`, `companies`, `career`, or `domain`.
- `get_company` requires `company_id`.
- `update_company` requires `company_id`; supplied fields are forwarded to the backend company update RPC.
- `create_job` requires `company_id`, `title`, and `description`; status defaults to `open` and source defaults to `manual` when not provided.
- `search_jobs` accepts optional keyword, company ID, location, remote type, employment type, status, and source.
- `get_job` and `close_job` require `job_id`.
- `list_applications_for_job` requires `job_id` and accepts optional application status.
- `update_application_status` requires `application_id` and status. Expected statuses include `submitted`, `reviewing`, `interview`, `rejected`, `offered`, and `withdrawn`.

Current output behavior:

- Tool results are JSON strings returned to the OpenAI tool loop.
- Customer mutations return `{"created_customer": ...}`.
- Customer reads return `{"customers": [...]}`.
- Service reads return `{"services": [...]}`.
- Assignment mutations return `{"customer_service": ...}`.
- Order reads/mutations return `{"order": ...}` or `{"orders": [...]}`.
- Company reads/mutations return `{"company": ...}` or `{"companies": [...]}`.
- Job reads/mutations return `{"job": ...}` or `{"jobs": [...]}`.
- Application reads/mutations return `{"application": ...}` or `{"applications": [...]}`.

## Platform gRPC Client Standard

The AI service must use the platform client as the only backend integration layer.

Current client path:

```text
apps-repo/ai/ceerat-agent-service/internal/platform/client.go
```

Current client structure:

```text
platform.Client
  conn      *grpc.ClientConn
  auth      auth.AuthClient
  customers customer.CustomerServiceClient
  services  service.ServiceManagerClient
  orders    order.OrderManagerClient
  profiles  career.CareerProfileServiceClient
  jobs      career.JobServiceClient
  carts     career.JobCartServiceClient
  apps      career.JobApplicationServiceClient
  threads   ai.AIThreadServiceClient
```

Current session structure:

```text
platform.Session
  Token  string
  UserID string
  User   SessionUser
```

Connection rules:

- The client connects to `CEERAT_USER_SERVICE_ADDR`, defaulting locally to `localhost:50051`.
- The older `USER_SERVICE_ADDR` fallback may exist for compatibility, but new docs and setup should prefer `CEERAT_USER_SERVICE_ADDR`.
- Local development currently uses insecure gRPC transport. Production hardening should move toward TLS/mTLS without changing tool semantics.
- The client should expose typed methods that accept Go/protobuf values, not raw model strings beyond tool argument parsing.

Authentication rules:

- `ValidateSession(ctx, bearerToken)` strips the `Bearer ` prefix, calls `auth.Auth/ValidateToken`, and rejects invalid tokens.
- `ValidateSession` reads the sanitized authenticated user returned by `auth.Auth/ValidateToken`; callers must not decode JWT payloads locally after validation.
- Agent and customer chat may use sanitized `ValidateToken.user` session context for first-party account questions such as name, email, role, and status. Do not source this identity from browser/model text or decoded JWT payloads.
- `ToolRunner.Run` must attach the authenticated token to context with `platform.ContextWithToken`.
- `platform.Client` must append outgoing gRPC metadata:

```text
authorization: Bearer <jwt>
```

- Every platform client method that reaches `ceerat-user-service` must call the outgoing auth context helper before invoking gRPC.
- Never log raw JWTs, authorization headers, or full request metadata.

User scoping rules:

- Customer and order calls should pass `session.UserID` or the user ID extracted by `ValidateSession`.
- Tools must not accept `user_id` from the model or browser for authenticated user-scoped operations.
- If a protobuf request needs `UserId`, the platform client should set it from the session, not from free-form user input.
- Customer-facing AI tools must use customer-owned RPCs that derive `customer_id` from the authenticated JWT by looking up `customers.user_id`; do not accept a model-supplied `customer_id`.
- If customer tools return permission errors for `who am I`, `my profile`, `list my skills`, or similar customer-owned requests, first verify the logged-in portal session is an active customer. An active agent/admin token in `ceerat-customer-ui` is a portal-boundary bug, not an AI prompt/tool-selection problem.
- Backend RBAC and repository ownership checks remain the final authority.

Thread scoping rules:

- Agent profile history is scoped as authenticated user + `THREAD_PROFILE_AGENT` + external thread id.
- Customer profile history is scoped as authenticated user + `THREAD_PROFILE_CUSTOMER` + external thread id.
- The browser may provide an external `session_id`, but must not provide or control the persisted user id.
- The old in-memory history keying pattern should not be reintroduced. Durable history belongs in `ai.AIThreadService`.

Error handling rules:

- gRPC errors should be returned to the caller and converted by `/agent/chat` into an HTTP error response.
- Protobuf domain errors, when present in a response, should be converted to Go errors before the tool result is returned.
- Tool argument validation errors should be explicit, such as `first_name and last_name are required`.
- Missing or ambiguous business entities should result in a clarification question or a read tool call, not invented IDs.

## Tool Calling Loop Standard

The chat implementation should follow this pattern:

```text
HTTP /agent/chat
  -> validate bearer token through platform.Client.ValidateSession
  -> decode/validate ChatRequest
  -> create bounded request context
  -> Agent.Chat(session, session_id, message)
  -> GetOrCreateThread/GetThread from ai.AIThreadService
  -> prepend sanitized user/final-assistant history
  -> OpenAI chat completion with toolDefinitions()
  -> model requests one or more tool calls
  -> ToolRunner.Run parses JSON arguments
  -> ToolRunner calls platform.Client
  -> JSON tool result is sent back to OpenAI
  -> AppendMessage user + final assistant to ai.AIThreadService
  -> final assistant reply plus action names returned to web UI
```

The current implementation limits one chat request to four tool-calling rounds. Keep a bounded loop so a bad prompt, bad tool schema, or model confusion cannot create an unbounded backend operation.

For customer chat, use the same loop with:

```text
HTTP /customer/chat
  -> validate bearer token through platform.Client.ValidateSession
  -> Agent.CustomerChat(session, session_id, message)
  -> GetOrCreateThread/GetThread from ai.AIThreadService with customer profile
  -> customer self-service system prompt
  -> customerToolDefinitions()
  -> ToolRunner.RunCustomer
  -> backend gRPC services enforce JWT/RBAC/ownership
  -> AppendMessage user + final assistant to ai.AIThreadService
```

Do not route customer portal chat to `/agent/chat`. Do not expose agent/admin tools through `RunCustomer`.

## Tool Design Rules

AI tools should be:

- Explicit.
- Narrow.
- Permission-checked.
- Auditable.
- Backed by service APIs.
- Separated into read tools and mutation tools.

Tools must not:

- Write directly to PostgreSQL.
- Bypass service APIs.
- Bypass RBAC.
- Invent customer/order/service IDs.
- Store raw JWTs in logs.
- Hide destructive operations from the user.

## Required Tool Plan Details

For each planned tool, include:

- Tool name.
- Read or mutation category.
- Input schema.
- Output schema.
- Backend gRPC/admin HTTP method used.
- Platform client method to add or reuse.
- Proto package and RPC that must exist in contracts.
- Whether `session.UserID` must be injected.
- Whether outgoing authorization metadata is required.
- Required role/permission.
- Ownership/scoping behavior.
- Business event emitted.
- Error behavior.
- Tests.

For every new gRPC-backed tool, the implementation plan must include:

1. Add or update the protobuf RPC and generated contracts.
2. Add the service implementation and repository behavior in the owning backend service.
3. Register the method in `KnownGRPCMethods`.
4. Add the permission to `DefaultRolePermissions`.
5. Add or reuse a `platform.Client` method that forwards auth metadata.
6. Add the OpenAI tool schema in `toolDefinitions()`.
7. Add a `ToolRunner.Run` case.
8. Add tests for valid arguments, missing arguments, backend error, RBAC/ownership denial, and successful JSON result shape.
9. Update `apps-repo/ai/docs/agent-tools.md` and this standard if the new tool is generally available.

## ID and Data Rules

When a tool needs an existing entity:

1. Resolve it through an approved list/get API.
2. Ask for clarification if multiple matches exist.
3. Use the real ID returned by the platform.
4. Include that ID in the mutation request.

For example:

- Before assigning a service to a customer, resolve the customer and service through list/get APIs if the user supplied names instead of IDs.
- Before creating an order, resolve every requested service to a real `service_id`.
- Before removing an order service line, get the order first if the user refers to a service line by name or description.
- If the user asks for companies, use `list_companies`.
- Before creating or renaming a career company, search with `list_companies` using the proposed real name. If a likely existing company appears, ask for confirmation instead of creating a duplicate. Backend duplicate validation remains the final authority.
- Before creating a career job from a company name, use `list_companies` to resolve the company. If multiple companies match, ask the user to choose.
- Before closing a career job from a title, use `search_jobs` to resolve the job. If multiple jobs match, ask the user to choose.
- Before updating an application status from a natural language applicant/job reference, use job/application list APIs to resolve a real `application_id`.

The model may explain what it is doing, but the mutation must use real platform IDs from service APIs.

## Security and Ownership

Tools execute with the user's Ceerat JWT. Backend services still enforce JWT validity, RBAC, customer ownership, admin-only access, and repository-level scoping.

The AI tool layer improves the interface; it is not the security boundary.

Security invariants:

- A tool may make a workflow easier, but it must never grant a permission the user does not already have.
- The agent service should validate the session once at the HTTP boundary and forward the same token to backend gRPC calls.
- Backend services must still run JWT interceptors, RBAC checks, ownership checks, and repository scoping.
- Admin-only tools must be separate from customer/user tools and must require explicit admin RBAC permissions.
- App portals should reject wrong-role sessions before forwarding chat requests. `ceerat-web-ui` is active-agent-only; `ceerat-customer-ui` is active-customer-only. This avoids confusing AI responses caused by backend tools correctly denying the wrong role.
- Destructive or high-impact tools should ask for confirmation unless the user request is already explicit and unambiguous.

## Local AI Stack Setup

For a complete local chat path, these services must be running:

```text
PostgreSQL
ceerat-user-service       gRPC localhost:50051
ceerat-agent-service      HTTP localhost:8088
ceerat-web-ui             HTTP localhost:3000
ceerat-customer-ui        HTTP localhost:3005
```

Important agent service environment:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
CEERAT_USER_SERVICE_ADDR=localhost:50051
PORT=8088
```

Important web UI environment:

```text
CEERAT_WEB_UI_PORT=3000
CEERAT_API_BASE_URL=localhost:50051
CEERAT_AGENT_BASE_URL=http://localhost:8088
CEERAT_ENV=local
```

Preferred local startup from `infra`:

```text
make start-stack
```

Useful logs:

```text
logs/agent-service.log
logs/web-ui.log
logs/customer-ui.log
logs/user-service.log
```

Customer chat smoke tests after implementation:

```text
1. Log in to ceerat-customer-ui as an active customer.
2. Open http://localhost:3005/chatgpt-client/ or the customer chat launcher.
3. Ask "who am I" and confirm the assistant uses `get_my_customer_profile`.
4. Ask "list my skills" and confirm the assistant uses `list_my_skill_profiles`.
5. Confirm an agent/admin account cannot keep a customer portal session.
```

## Business Events and Intelligence

Mutation tools should emit or trigger structured business events for future BI/intelligence.

Examples:

```text
agent.tool_invoked
agent.tool_failed
service.recommended
service.assigned_to_customer
order.created
order.status_updated
discount.offered
```

Events should go to a separate BI/analytics store when implemented. Analytics failures must not roll back OLTP transactions.

Future insight types may include:

```text
conversion_opportunity
customer_retention_risk
agent_performance_signal
service_pricing_recommendation
discount_experiment
operational_bottleneck
executive_summary
```
