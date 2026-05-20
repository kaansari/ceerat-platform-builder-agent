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

## UI Surfaces

| UI | Purpose | Backend dependency |
| --- | --- | --- |
| Admin UI | Admin users, roles, permissions, RBAC cache, operational controls | User service admin HTTP API |
| Web UI | Authenticated operational app, dashboard, orders, AI Agent panel, full-page `/chatgpt-client/` | User service gRPC, agent service HTTP |
| Customer UI | Customer registration and self-service workflows | User service gRPC |

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
- Server-side JWT forwarding to gRPC or agent service.
- Redaction of passwords, tokens, secrets, and keys in logs.

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

Both must forward through `ceerat-web-ui` to `ceerat-agent-service`; neither should call OpenAI directly.

## Admin and Executive Intelligence UI

Future AI summaries and recommendations belong in admin/executive surfaces. They should be based on structured BI events and insights, not raw logs.

Plans should include review states such as new, reviewed, accepted, dismissed, and implemented when proposing AI insights.
