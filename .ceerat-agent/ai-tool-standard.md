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
- Required role/permission.
- Ownership/scoping behavior.
- Business event emitted.
- Error behavior.
- Tests.

## ID and Data Rules

When a tool needs an existing entity:

1. Resolve it through an approved list/get API.
2. Ask for clarification if multiple matches exist.
3. Use the real ID returned by the platform.
4. Include that ID in the mutation request.

## Security and Ownership

Tools execute with the user's Ceerat JWT. Backend services still enforce JWT validity, RBAC, customer ownership, admin-only access, and repository-level scoping.

The AI tool layer improves the interface; it is not the security boundary.

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

