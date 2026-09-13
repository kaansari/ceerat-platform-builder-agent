# Public AI Integration Security Profile

This profile defines the minimum security architecture for exposing CEERAT
operations to ChatGPT, Codex, or another public MCP-compatible AI client. It is
a reusable platform standard. Dated deployment evidence belongs in the owning
project's milestone or operations documentation.

## Required trust boundaries

```text
AI client
  -> HTTPS MCP + external OAuth bearer token
public CEERAT agent gateway
  -> authenticated private service channel
CEERAT backend service
  -> ownership-scoped persistence
PostgreSQL
```

The gateway is a policy-enforcement point, not a transparent proxy. External
OAuth tokens terminate at the gateway and must not be reused as internal
service JWTs. Backend services remain authoritative for RBAC, record ownership,
business validation, and persistence.

For consequential commerce tools, expose a read-only quote/preview followed by
a confirmation bound to an expiring server fingerprint, optimistic version, and
idempotency key. Reconnect reconciliation reads a durable subject-scoped
operation outcome and must never repeat the mutation. Keep the public tool
disabled until schema migration, preflight, matching private-gRPC binary, and a
private smoke test are all verified live.

## OAuth and client requirements

- Publish RFC 9728-compatible OAuth Protected Resource Metadata and standard
  authorization-server or OIDC discovery.
- For Keycloak-backed MCP, use Keycloak 26.4.0 or newer and expose the root
  `/.well-known/oauth-authorization-server/realms/{realm}` RFC 8414 route.
  Acceptance tests must fetch that exact issuer-derived route; checking only
  the realm-local OIDC discovery document is insufficient for MCP clients.
- Use authorization code with PKCE `S256` for user-delegated clients.
- Hosted ChatGPT may use a predefined confidential client whose secret is held
  only in ChatGPT's protected app configuration. Native Codex uses a public
  client with token endpoint authentication method `none`. Never place either
  client's credentials or tokens in a prompt, tool result, log, or repository.
- Match resource indicator, token audience, issuer, and redirect URI exactly.
- Allow only registered redirect URIs. Support the client-specific callback
  displayed by ChatGPT when stable callback discovery is unavailable.
- Grant only documented scopes. `offline_access` must be explicitly allowed
  when requested and refresh tokens must remain outside model context.
- Keep protected-resource `scopes_supported`, authorization-client optional
  assignments, human consent text, and the app's requested scope list in sync.
  Adding an optional scope does not upgrade an existing grant: deploy metadata
  first, then require a fresh authorization and verify only decoded scope names.
- Keep domain scopes narrow and composable. Separate read, create/checkout,
  and post-creation mutation authority when their risk differs. A catalog,
  self-cart, or self-order scope grants an operation category only; it never
  grants ownership, price, inventory, state-transition, tenant-selection, or
  administrative authority.
- Require HTTPS for all public metadata, authorization, token, JWKS, and MCP
  endpoints.

## Access-token validation

Before dispatching any protected tool, the gateway must validate:

- supported asymmetric signing algorithm and signature using current JWKS;
- exact trusted issuer;
- expected MCP resource audience;
- expiry and not-before timestamps with bounded clock skew;
- authorized client claim such as `azp`, matched against an explicit allowlist;
- stable CEERAT identity mapping claim;
- every scope required by the selected operation.

Identity, role, scope, user ID, customer ID, connection ID ownership, and grant
authority must never be accepted from model-controlled arguments. A fallback
when `sub` is absent is permitted only when it uses a separately configured,
validated, stable CEERAT identity claim.

The client allowlist is independent of issuer and audience checks. During a
bounded migration it may include a named rollback client; remove that ID when
the rollback client is disabled.

## Session revocation

- Use the validated `sid` plus OAuth client ID as the durable local connection
  key across access-token rotation; keep `jti` only as token-level metadata.
- Mark the owned connection revoked before the authorization-server request so
  timeouts cannot restore gateway access.
- Delete the matching normal/offline Keycloak session according to the
  validated `offline_access` grant. Never retain a refresh token merely to make
  gateway-side revocation possible.
- Treat 204 and an already-absent 404 as idempotent success. Treat timeout,
  denial, or malformed service authentication as `OUTCOME_UNKNOWN` while the
  local deny decision remains effective.
- Keycloak's supported admin operation targets a user session. If multiple
  CEERAT clients share that SSO session, all can be signed out; tool descriptions
  and confirmation UX must state that blast radius.
- Keep the revoker credential in the deployment secret manager. Grant only the
  minimum supported Keycloak permission and document any residual breadth of a
  built-in role.

The CEERAT Phase 1 live test on 2026-09-03 confirmed this sequence: a mismatched
revoker credential produced fail-closed `OUTCOME_UNKNOWN`; coordinated secret
rotation allowed confirmed Keycloak session deletion; and the next ChatGPT
request required reconnection. Preserve independent secrets for the hosted
ChatGPT client and gateway revoker, and preserve the ChatGPT secret during
idempotent client reconciliation.

## Identity lifecycle

OAuth login and CEERAT registration are distinct operations. A production
self-service flow must recoverably:

1. create or locate the identity-provider account;
2. create the CEERAT customer-role user;
3. create and link the customer profile;
4. store an immutable provider-subject-to-CEERAT-user mapping;
5. issue tokens containing the authorized CEERAT identity claim;
6. handle retries without creating duplicate users or profiles.

Manual attribute editing, direct SQL linking, and arbitrary caller-supplied
user IDs are development-only practices.

## Gateway-to-service authentication

Private networking is not authentication. Production gateways must use a
dedicated workload identity and an audience-restricted internal
assertion/token-exchange contract. The service must verify the gateway workload,
the external identity mapping, the exchange audience, expiry, and replay
protection before issuing or accepting an internal user context.

An endpoint that mints a user token from an unauthenticated caller-supplied ID
is prohibited. Legacy ID-based authentication may be used only in an isolated
development environment, must not be generally reachable, and is a release
blocker until removed.

## Tool-contract controls

- Expose a small allowlisted tool surface with strict JSON Schemas.
- Reject unknown model-controlled fields, while accepting reserved protocol
  metadata such as MCP `params._meta` separately from business inputs.
- Enforce closed schemas in runtime decoding for no-argument tools, nested
  objects, public tools, and protected tools; schema publication alone is not a
  security control.
- Derive ownership from authenticated identity, never from tool arguments.
- Annotate read-only, consequential, and destructive tools accurately, but do
  not rely on annotations as enforcement.
- Split consequential changes into prepare and execute operations when a useful
  preview can be produced.
- Require explicit `confirmed: true` and a short-lived, user-bound,
  operation-bound preparation identifier for consequential execution.
- Validate published schemas with every supported hosted AI client. Avoid
  contradictory outer/branch `additionalProperties` composition. If a client
  cannot safely consume a top-level polymorphic input, use separate tools or a
  flat closed schema plus strict runtime argument-shape validation; do not
  weaken ownership, confirmation, or unknown-field rejection.
- Refresh/version the registered hosted-client app after schema changes and
  verify the imported definition. Starting a new conversation is not a schema
  refresh guarantee.
- Require idempotency keys for retryable writes and retain results long enough
  to cover realistic client retry windows.
- Apply request-size, rate, concurrency, and downstream timeout limits.
- Authentication-only tools may use an empty additional-scope requirement after
  full bearer-token validation. Do not treat absence of `openid` from an access
  token's scope claim as an authentication failure when the authorization
  server has otherwise issued a valid token for the protected resource.

## LLM-safe errors

Every tool result should use a stable envelope that lets an AI client decide
whether to retry, ask the user, reauthenticate, correct input, or stop. Errors
should include only safe fields such as:

```text
code
category
user_message
retryable
agent_action
safe_details
request_id
operation_state
required_scopes (when applicable)
```

Do not return raw OAuth responses, token-validation internals, claims,
credentials, stack traces, SQL errors, private hostnames, or upstream payloads.
Log a sanitized technical reason server-side with the same request ID, tool
name, and operation state. Never log authorization codes, passwords, cookies,
access tokens, refresh tokens, client secrets, or password-reset values.

## Session, revocation, and state

- Store preparations, grants, connection records, idempotency records, and
  revocation state in durable shared storage for multi-instance deployments.
- Bind records to user, client, scopes, operation, resource version, creation
  time, and expiry as appropriate.
- Keep gateway authorization state (`active` or `revoked`) distinct from the
  observed access-token state (`valid` or `expired`). Access-token expiry must
  not be presented as verified authorization-server or refresh-family status.
- Derive the current connection from the validated token identifier and return
  an explicit `is_current`; never accept current/owner identity from tool
  arguments.
- Persist `created_at`, `last_used_at`, and `access_token_expires_at` as
  server-owned timestamps. Repeated and concurrent observation of the same
  connection must update it idempotently rather than create duplicates.
- Make logout and connection revocation explicit, auditable operations.
- Integrate authorization-server token/session revocation; deleting only a
  gateway process-local record is not sufficient.
- Fail closed when revocation or identity state cannot be established for a
  consequential operation.

## Data and deployment isolation

- Give each runtime component a least-privilege database user.
- Keep Keycloak and CEERAT application tables in separate schemas at minimum;
  separate databases are preferred where risk or scale warrants it.
- Do not share a generic `public` schema between independently migrating
  products because table names and migration ownership can collide.
- Keep backend gRPC endpoints private and expose only the HTTPS gateway.
- Pin trusted issuers, audiences, algorithms, and internal service endpoints
  through deployment configuration with safe startup validation.

## Production verification gate

Before public release, automated and human tests must demonstrate:

- unauthenticated discovery works but protected calls fail with a correct OAuth
  challenge and safe structured error;
- authorization-code + PKCE login succeeds from every supported client;
- invalid signature, issuer, audience, client, expiry, identity, and scope are
  rejected without information leakage;
- registration provisions exactly one linked CEERAT user and customer under
  retry and partial-failure scenarios;
- current-user and owned-resource reads cannot cross tenant boundaries;
- write preview, confirmation, stale-version, idempotency, and replay controls
  behave as documented;
- logout and revocation prevent subsequent protected use within the stated
  propagation window;
- model metadata cannot bypass schema validation;
- secrets and tokens are absent from client results, logs, traces, and audit
  payloads;
- gateway workload authentication and internal token exchange fail closed;
- restart and horizontal-instance tests preserve preparation, connection,
  idempotency, and revocation behavior.

Passing interoperability tests proves client compatibility. It does not by
itself establish production readiness; every production gate above must be
closed or explicitly risk-accepted by the security owner.
