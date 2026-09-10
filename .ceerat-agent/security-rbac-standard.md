# Security and RBAC Standard

Backend services are the security boundary. Apps and AI agents call backend APIs; they do not write directly to the OLTP database.

For the complete reusable gateway checklist and production verification gate,
apply `public-ai-integration-security-profile.md` together with this standard.

## External MCP OAuth Standard

For public ChatGPT, Codex or compatible MCP integrations, apply all of these
validated rules:

1. Publish OAuth Protected Resource Metadata and authorization-server/OIDC
   discovery. The MCP resource identifier and JWT audience must match exactly.
2. Use authorization code + PKCE `S256` for customer delegation. Public clients
   use token endpoint auth method `none`; confidential predefined clients may
   use an explicitly configured supported client-authentication method.
3. Treat OAuth and bearer authentication as complementary: OAuth obtains and
   refreshes the credential; every protected MCP call sends the access token in
   the HTTP `Authorization` header.
4. Validate RS256 signature through JWKS, issuer, audience, expiry/not-before,
   configured client claim against an explicit allowed-client list, configured
   CEERAT identity claim and scopes. Audience validation does not replace the
   client allowlist. Never trust identity, role, scope, customer ID or grant ID
   from tool arguments.
5. Keep credential entry and consent on a CEERAT-controlled authorization page.
   Passwords, MFA/recovery values, codes, cookies, access/refresh tokens and
   client secrets must not enter prompts, tool arguments, structured results,
   logs or audit payloads.
6. Use exact redirect URI matching. Support ChatGPT's exact callback-specific
   URI unless the provider correctly advertises and returns RFC 9207 issuer
   identification for the stable callback.
7. If ChatGPT requests `offline_access`, the client must be explicitly allowed
   that scope. Refresh-token use and revocation remain between the MCP host and
   authorization server, outside model context.
8. Define custom identity attributes in the Keycloak declarative user profile.
   Keycloak 26 can discard undefined attributes, preventing token mappers from
   emitting them. `ceerat_user_id` is administrator-managed and maps to an
   active CEERAT customer-role user.
9. A missing `sub` may fall back only to a separately configured and validated
   stable CEERAT identity claim. A missing client or CEERAT identity claim is
   an authentication failure.
10. Public errors reveal only stable OAuth/CEERAT codes, required scopes and
    safe recovery actions. Log the detailed validation reason server-side with
    request/tool correlation, never the credential.
11. Split domain authorization by materially different operation classes. In
    particular, order read, cart checkout/order creation, and eligible-order
    mutation use distinct optional scopes; none replaces subject-derived
    ownership, state-machine, confirmation, idempotency, or downstream RBAC.

Authentication success at the authorization server does not establish a
CEERAT customer. Registration provisioning must atomically or recoverably
create/link the CEERAT user and customer, store the identity mapping, and avoid
direct SQL from the gateway. Until that workflow exists, manual linking is a
development-only operation.

For MCP connection logout, bind local state to the validated authorization
server session claim plus client ID, not the access-token `jti`; `jti` changes
on refresh. Revoke locally before calling the authorization server, and report
`OUTCOME_UNKNOWN` if upstream deletion cannot be confirmed. Store only the
opaque session identifier, never access/refresh tokens or authorization codes.
Keycloak's supported session-delete API removes a user/offline session rather
than one child client session, so public tools must disclose that clients
sharing that SSO session may also be signed out. A service revoker must be
service-account-only, secret-managed, and limited to the minimum supported
session-management permission; never grant `realm-admin`.

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
- Customer Career profile, resume, job cart, application, and calendar event access resolves the authenticated user through `customers.user_id`; do not trust customer-supplied `customer_id`.
- Customer employment records and resume-employment attachments resolve ownership through authenticated `customers.user_id`. Attachment mutations must verify ownership of both the resume and the employment record.
- Customer Career workflow metrics resolve customer identity from authenticated context. Global market metrics may be customer-readable only as sanitized aggregate counts/buckets with no private customer or application details.
- Customer resume downloads must resolve `customer_id` from authenticated context and fetch by `customer_id` plus `resume_id` before returning PDF bytes.
- Customer external ATS application submissions must resolve `customer_id` from authenticated context, require explicit confirmation, validate resume ownership, derive any internal skill profile from that resume, and store only sanitized provider status/audit summaries.
- Customer career calendar methods are protected self-service methods under `calendar.CalendarService`. They belong in `KnownGRPCMethods` and customer default role permissions, but never in `DefaultPublicMethods`.
- Customer service assignments are filtered or denied by owner.
- Customer cart access uses only self-scoped `*MyCart*` contracts, resolves the
  authenticated user to its own customer profile, and exposes no customer/user
  selector to public MCP clients. The private gRPC service repeats ownership,
  product visibility, version, and idempotency enforcement independently of the
  gateway.
- Order reads and writes are scoped by authenticated user id.
- Customer address updates derive customer identity from JWT and may update only the caller's shipping and billing addresses.
- Customer cart quote/checkout derives customer, cart, shipping address, billing address, tax jurisdiction, prices, and totals server-side.
- Agents/admins manage tax, shipping, and coupon rules. Customers cannot list or mutate pricing rules and cannot reprice arbitrary orders.
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

## Order Pricing And Address RBAC

All customer, order-pricing, coupon, tax, and shipping methods remain protected. None belong in `DefaultPublicMethods`.

Customer default permissions include:

```text
/customer.CustomerService/GetMyCustomerProfile
/customer.CustomerService/UpdateMyCustomerProfile
/order.OrderManager/QuoteMyCartPricing
/order.OrderManager/CheckoutMyCart
/order.OrderManager/GetMyOrder
/order.OrderManager/ListMyOrders
/order.OrderManager/PreviewMyOrderUpdate
/order.OrderManager/UpdateMyOrder
/order.OrderManager/PreviewMyOrderCancellation
/order.OrderManager/CancelMyOrder
/order.OrderManager/GetMyOrderOperationStatus
```

Agent default permissions include:

```text
/order.OrderManager/RepriceOrder
/order.OrderManager/CreateOrderPricingRule
/order.OrderManager/ListOrderPricingRules
/order.OrderManager/UpdateOrderPricingRule
/order.OrderManager/DeleteOrderPricingRule
```

Security rules:

- Customer quote/checkout accepts no trusted customer id, tax state, address, unit price, discount, shipping charge, tax, or total from the browser.
- Customer order requests never accept identity, ownership, role, scope,
  lifecycle status, payment status, line items, or monetary totals. Identity is
  derived from authenticated gRPC context on every preview, confirmation, and
  operation-status call.
- Tax jurisdiction is resolved from the authenticated customer's explicit shipping address or the immutable order shipping snapshot.
- Billing address is persisted/snapshotted but never used as tax jurisdiction.
- Coupon eligibility and shipping-method availability are recalculated server-side.
- `RepriceOrder` stays user-scoped in the repository.
- Pricing-rule writes are agent/admin only; customer role can consume only the sanitized quote result.
- Reject incomplete addresses and stale shipping selections. Do not widen access or add public/legacy bypasses.

## Current Customer Career RBAC Methods

Customer Career self-service methods include these protected gRPC methods:

```text
/career.CareerProfileService/CreateSkillProfile
/career.CareerProfileService/ListMySkillProfiles
/career.CareerProfileService/AddSkillToProfile
/career.CareerProfileService/UpdateSkillInProfile
/career.CareerProfileService/BatchAddSkillsToProfile
/career.CareerProfileService/CreateResume
/career.CareerProfileService/ListMyResumes
/career.CareerProfileService/UpdateResume
/career.CareerProfileService/DeleteResume
/career.CareerProfileService/DownloadResume
/career.CareerProfileService/ParseResumeText
/career.CareerProfileService/ImportResumeDraft
/career.CareerProfileService/CreateEmploymentRecord
/career.CareerProfileService/BatchCreateEmploymentRecords
/career.CareerProfileService/ListMyEmploymentRecords
/career.CareerProfileService/GetEmploymentRecord
/career.CareerProfileService/UpdateEmploymentRecord
/career.CareerProfileService/ArchiveEmploymentRecord
/career.CareerProfileService/AttachEmploymentRecordToResume
/career.CareerProfileService/BatchAttachEmploymentRecordsToResume
/career.CareerProfileService/DetachEmploymentRecordFromResume
/career.CareerProfileService/UpdateResumeEmploymentRecord
/career.CareerProfileService/ListResumeEmploymentRecords
/career.CareerProfileService/GetMyCareerMetrics
/career.JobService/GetJob
/career.JobService/SearchJobs
/career.JobService/GetCareerMarketMetrics
/career.JobCartService/GetJobCart
/career.JobCartService/AddJobToCart
/career.JobCartService/UpdateCartItemProfile
/career.JobCartService/RemoveJobFromCart
/career.JobCartService/ClearJobCart
/career.JobApplicationService/ApplyToJob
/career.JobApplicationService/DiscoverJobApplication
/career.JobApplicationService/SubmitJobApplication
/career.JobApplicationService/ApplyToCartJobs
/career.JobApplicationService/ListMyApplications
/career.JobApplicationService/GetMyApplication
/calendar.CalendarService/ListMyCalendarEvents
/calendar.CalendarService/GetMyCalendarEvent
/calendar.CalendarService/CreateCalendarEvent
/calendar.CalendarService/UpdateCalendarEvent
/calendar.CalendarService/DeleteCalendarEvent
```

Customer Career RBAC must not include agent/admin operational mutations:

```text
/career.JobService/CreateCompany
/career.JobService/UpdateCompany
/career.JobService/CreateJob
/career.JobService/UpdateJob
/career.JobService/CloseJob
/career.JobService/ReopenJob
/career.JobService/ImportATSJobs
/career.JobApplicationService/ListApplications
/career.JobApplicationService/GetApplication
/career.JobApplicationService/UpdateApplicationStatus
```

## Admin Operations Rules

Admin and operational APIs should be protected gRPC methods on `admin.AdminService`, not a separate backend admin HTTP server.

Admin gRPC methods must:

1. Use the normal JWT, RBAC, and logging interceptors.
2. Load the current user from the database or identity source.
3. Require an active `role == "admin"` user before sensitive operations.
4. Apply the operation through service-owned repositories.
5. Refresh affected in-memory caches before returning success.
6. Return sanitized protobuf responses or canonical gRPC errors.

Browser admin UIs may expose same-origin HTTP endpoints, but those app routes must forward to protected backend gRPC clients and must not bypass the service security boundary.

## Test Requirements

Plans must include tests for missing token, invalid token, RBAC denied, RBAC allowed, ownership denied, ownership allowed, admin-only gRPC methods, and AI tool permission behavior when tools are involved.

Public MCP changes additionally require tests for protected-resource discovery,
authorization code + PKCE, exact redirect matching, issuer/audience/client and
identity claims, missing/expired/wrong-audience tokens, scope denial,
`offline_access` compatibility where requested, reserved MCP `_meta`,
anti-enumerating OAuth challenges, structured error redaction, private gRPC
RBAC/ownership, confirmation enforcement, connection revocation, and at least
two real MCP clients. The Phase 1 baseline clients are Codex and ChatGPT.
