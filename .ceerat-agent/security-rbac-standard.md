# Security and RBAC Standard

Backend services are the security boundary. Apps and AI agents call backend APIs; they do not write directly to the OLTP database.

## gRPC Security Flow

Protected gRPC calls flow through:

```text
JWT interceptor
  -> RBAC interceptor
  -> logging interceptor
  -> handler ownership checks
  -> repository scoped query/write
```

Use RBAC for:

```text
Can this role call this method?
```

Use handler/repository checks for:

```text
Can this user access this record?
```

## Shared Security Hooks

Use these shared hooks from `contracts-repo/packages/ceerat-contracts/security`:

| Hook | Purpose |
| --- | --- |
| `DefaultPublicMethods` | Exact methods that bypass JWT/RBAC. |
| `KnownGRPCMethods` | Methods admin/RBAC tooling can assign permissions for. |
| `DefaultRolePermissions` | Seed permissions for default roles. |
| `NewJWTInterceptor` | Validates token and injects authenticated user context. |
| `NewRBACInterceptor` | Checks role permission for the current gRPC method. |
| `AuthenticatedUserFromContext` | Handler hook to read authenticated user identity. |
| `WithAuthenticatedUser` | Test helper to attach identity to context. |

## JWT Rules

Protected calls must send:

```text
authorization: Bearer <jwt>
```

Also accepted:

```text
x-auth-token: <jwt>
```

JWT values must never be logged. JWT claims should exclude passwords and token fields.
Auth validation responses should return sanitized current user claims from the auth service. Callers must not decode JWT payloads locally after `auth.Auth/ValidateToken`.

## Public Method Rules

Public methods must be rare. Good candidates:

- Login.
- Registration.
- Token validation.
- Health check.

Bad public candidates:

- List data.
- Mutate business records.
- Admin operations.
- AI tool execution.

When a plan adds a public method, it must explain why and list the exact full method name.

## RBAC Method Rules

RBAC uses exact gRPC method names:

```text
/package.Service/Method
```

Plans must add new protected methods to:

```text
security.KnownGRPCMethods
security.DefaultRolePermissions
```

Default role pattern:

- `admin`: usually wildcard `*`.
- `agent`: operational methods required for internal work.
- `customer`: self-service methods only.

## Ownership Rules

Customer-owned data must be scoped to the authenticated user.

Examples:

- Customer can only read/update its own user profile.
- Customer cannot list all customers.
- Customer profile access checks `customers.user_id`.
- Customer Career profile, resume, job cart, and application access resolves the authenticated user through `customers.user_id`; do not trust customer-supplied `customer_id`.
- Customer resume downloads must resolve `customer_id` from authenticated context and fetch by `customer_id` plus `resume_id` before returning PDF bytes.
- Customer external ATS application submissions must resolve `customer_id` from authenticated context, require explicit confirmation, validate resume/profile ownership, and store only sanitized provider status/audit summaries.
- Customer service assignments are filtered or denied by owner.
- Customer cart access resolves the authenticated user to its own customer profile and denies another requested `customer_id`.
- Order reads and writes are scoped by authenticated user id.
- Product catalog reads are visibility-scoped: customer role can only read/list active products.
- Cart product items are visibility-scoped: customer role can add active products only.
- Product catalog writes are RBAC-scoped to admin/agent through `service.ServiceManager`.

Handler pattern:

```go
authUser, ok := security.AuthenticatedUserFromContext(ctx)
if !ok {
    return nil, status.Error(codes.Unauthenticated, "authentication required")
}
```

Repository pattern:

```text
WHERE id = ? AND user_id = ?
```

Cart ownership pattern:

```text
authenticated user id -> customers.user_id -> customer_id -> cart
```

Do not trust a customer-supplied `customer_id` for cart reads or writes. For customer role, either ignore the blank value and resolve ownership from context, or deny when the supplied `customer_id` differs from the authenticated user's customer profile.

AI customer tool ownership pattern:

```text
customer portal JWT -> auth user id -> customers.user_id -> customer-owned RPC
```

If a customer AI tool reports permission denied for a customer-owned action, check both layers:

1. The portal session must be an active customer session.
2. The backend method must remain protected by JWT, RBAC, and ownership checks.

Do not "fix" customer AI permission errors by making methods public, widening customer RBAC beyond self-service, or allowing customer tools to accept arbitrary `customer_id`.

## Admin HTTP Rules

Admin HTTP APIs must:

1. Read `Authorization: Bearer <jwt>` or `X-Auth-Token`.
2. Validate token.
3. Load current user.
4. Require `role == "admin"`.
5. Apply operation.
6. Refresh affected in-memory caches.
7. Return JSON.

Admin APIs should set:

```text
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
```

## Test Requirements

Plans must include tests for missing token, invalid token, RBAC denied, RBAC allowed, ownership denied, ownership allowed, admin-only routes, and AI tool permission behavior when tools are involved.
