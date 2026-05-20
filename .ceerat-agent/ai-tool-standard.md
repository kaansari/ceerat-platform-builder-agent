# AI Tool Standard

This file gives the builder agent rules for planning Ceerat AI tools and future intelligence features.

## Current Agent Boundary

`apps-repo/ai/ceerat-agent-service` is the active HTTP AI agent service. It validates a Ceerat JWT, calls OpenAI, and executes approved platform operations through backend service APIs.

Current endpoint:

```text
POST /agent/chat
```

Browser traffic reaches it through `ceerat-web-ui`:

```text
POST /api/agent/chat
POST /api/chatgpt-client/get-prompt-result
```

Current tools:

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
```

The actual browser UI remains in:

```text
apps-repo/apps/ceerat-web-ui/web/chatgpt-client
```

It is served by `ceerat-web-ui` at:

```text
http://localhost:3000/chatgpt-client/
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
  -> ceerat-web-ui same-origin route
  -> ceerat-agent-service POST /agent/chat
  -> OpenAI chat completion with tool definitions
  -> ToolRunner executes requested tool calls
  -> platform.Client sends gRPC with authorization metadata
  -> ceerat-user-service validates JWT/RBAC/ownership
  -> PostgreSQL through the service repository layer
```

The browser must not call OpenAI directly. The browser must not call gRPC directly. The agent service must not write directly to PostgreSQL.

## Active AI HTTP Routes

`ceerat-agent-service` exposes:

```text
GET  /healthz
POST /agent/chat
```

`POST /agent/chat` requires:

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
  "actions": ["list_customers"]
}
```

The agent service validates the bearer token before invoking the model. Invalid, missing, or malformed tokens must return an HTTP auth error before any tool execution.

## Web UI AI Routes

`ceerat-web-ui` owns browser-facing AI routes:

```text
GET  /chatgpt-client
GET  /chatgpt-client/
GET  /chatgpt-client/assets/...
POST /api/agent/chat
POST /api/chatgpt-client/get-prompt-result
```

Rules:

- `GET /chatgpt-client` redirects to `/chatgpt-client/`.
- `GET /chatgpt-client/` serves the full-page chat UI.
- `POST /api/agent/chat` forwards dashboard chat JSON to `ceerat-agent-service`.
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

## Existing Tool Implementation Files

Future tool work must start from these files:

```text
apps-repo/ai/ceerat-agent-service/internal/agent/tools.go
apps-repo/ai/ceerat-agent-service/internal/platform/client.go
apps-repo/ai/ceerat-agent-service/internal/httpapi/server.go
contracts-repo/packages/ceerat-contracts/proto/...
services-repo/services/ceerat-user-service/internal/security/...
```

Responsibilities:

- `internal/agent/tools.go` defines the OpenAI tool schemas and maps tool calls to platform client methods.
- `ToolRunner.Run` parses JSON tool arguments, attaches the session token to context, calls the platform client, and returns JSON string results to the OpenAI tool loop.
- `internal/platform/client.go` owns all gRPC clients and the JWT forwarding behavior.
- `internal/httpapi/server.go` owns `/agent/chat`, bearer token validation, request validation, timeout handling, and response shaping.
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

Current input behavior:

- `create_customer` requires `first_name` and `last_name`; address, email, and phone are optional.
- `list_customers` takes no arguments.
- `list_services` accepts optional `category` and `type`.
- `assign_service_to_customer` requires `customer_id` and `service_id`; `status` defaults to `ordered`; empty or `today` `ordered_at` becomes the current local date.
- `create_order` requires `customer_id` and `services`; service items require `service_id` and may include quantity, agent name, schedule/start/due dates.
- `list_orders` accepts optional `customer_id` and `status`.
- `get_order` requires `order_id`.
- `update_order_status` requires `order_id` and `status`.
- `add_service_to_order` requires `order_id` and `service_id`; service details may include quantity, agent name, schedule/start/due dates.
- `remove_service_from_order` requires `order_id` and `order_service_id`.

Current output behavior:

- Tool results are JSON strings returned to the OpenAI tool loop.
- Customer mutations return `{"created_customer": ...}`.
- Customer reads return `{"customers": [...]}`.
- Service reads return `{"services": [...]}`.
- Assignment mutations return `{"customer_service": ...}`.
- Order reads/mutations return `{"order": ...}` or `{"orders": [...]}`.

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
```

Current session structure:

```text
platform.Session
  Token  string
  UserID string
```

Connection rules:

- The client connects to `CEERAT_USER_SERVICE_ADDR`, defaulting locally to `localhost:50051`.
- The older `USER_SERVICE_ADDR` fallback may exist for compatibility, but new docs and setup should prefer `CEERAT_USER_SERVICE_ADDR`.
- Local development currently uses insecure gRPC transport. Production hardening should move toward TLS/mTLS without changing tool semantics.
- The client should expose typed methods that accept Go/protobuf values, not raw model strings beyond tool argument parsing.

Authentication rules:

- `ValidateSession(ctx, bearerToken)` strips the `Bearer ` prefix, calls `auth.Auth/ValidateToken`, and rejects invalid tokens.
- `ValidateSession` extracts `user.id` from the JWT payload into `Session.UserID`.
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
- Backend RBAC and repository ownership checks remain the final authority.

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
  -> OpenAI chat completion with toolDefinitions()
  -> model requests one or more tool calls
  -> ToolRunner.Run parses JSON arguments
  -> ToolRunner calls platform.Client
  -> JSON tool result is sent back to OpenAI
  -> final assistant reply plus action names returned to web UI
```

The current implementation limits one chat request to four tool-calling rounds. Keep a bounded loop so a bad prompt, bad tool schema, or model confusion cannot create an unbounded backend operation.

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

The model may explain what it is doing, but the mutation must use real platform IDs from service APIs.

## Security and Ownership

Tools execute with the user's Ceerat JWT. Backend services still enforce JWT validity, RBAC, customer ownership, admin-only access, and repository-level scoping.

The AI tool layer improves the interface; it is not the security boundary.

Security invariants:

- A tool may make a workflow easier, but it must never grant a permission the user does not already have.
- The agent service should validate the session once at the HTTP boundary and forward the same token to backend gRPC calls.
- Backend services must still run JWT interceptors, RBAC checks, ownership checks, and repository scoping.
- Admin-only tools must be separate from customer/user tools and must require explicit admin RBAC permissions.
- Destructive or high-impact tools should ask for confirmation unless the user request is already explicit and unambiguous.

## Local AI Stack Setup

For a complete local chat path, these services must be running:

```text
PostgreSQL
ceerat-user-service       gRPC localhost:50051
ceerat-agent-service      HTTP localhost:8088
ceerat-web-ui             HTTP localhost:3000
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
logs/user-service.log
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
