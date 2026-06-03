Create a structured services-only implementation plan for the requested Ceerat backend capability.

Use the loaded `.ceerat-agent` context and current platform patterns.

The plan must include:

- `module_name`: clear human-readable module name.
- `business_objects`: domain objects, relationships, ownership, statuses, and BI/business events.
- `required_protos`: protobuf messages, gRPC services/RPCs, full gRPC method names, contract/domain/mapper changes, and proto regeneration notes.
- `required_services`: backend ownership decision, handlers, repositories, startup wiring, admin HTTP hooks if needed, logging, infra/startup/config changes.
- `required_database_migrations`: OLTP tables, indexes, constraints, seed data, transactions, and separate BI/analytics tables if needed.
- `required_rbac_permissions`: exact gRPC methods for `KnownGRPCMethods`, default role permissions, public methods if any, admin-only requirements, and ownership checks.
- `required_logging_events`: structured service logs, business events, BI event handoff, redaction rules, and operational observability.
- `integration_impact`: existing app routes, AI tools, infra startup, logs, or callers that may need follow-up work by another agent; do not design frontend UI here.
- `required_tests`: contract, service, repository, security/RBAC, ownership, admin API, logging/event, migration, and infra/config tests.
- `risks_questions`: missing product decisions, ambiguous ownership, migration risks, security concerns, caller compatibility, BI/event open questions.

Planning rules:

- Do not generate code.
- Do not modify external repositories.
- Do not run git commands.
- Treat action words such as integrate, wire, connect, upgrade, implement, expose, add, update, fix, support, and enable as verbs, not domain nouns.
- Do not propose direct app or agent database writes.
- Do not design frontend pages, templates, CSS, browser behavior, or AI chat UI.
- Do not add UI implementation details to any field.
- Do not put persistence details in contracts.
- Keep public APIs minimal.
- Keep customer-owned data scoped to authenticated user identity.
- Include infra/log/config changes when a new process, port, environment variable, or log file is needed.
- Include BI/intelligence events for meaningful business behavior, using a separate analytics store rather than raw logs.
- Check `contracts-repo/docs/contract-inventory.json` and `services-repo/docs/grpc-service-inventory.json` before proposing new contracts or service boundaries.
- Check `apps-repo/docs/app-surface-inventory.json` only for integration impact and caller compatibility, not for UI design.
- If an existing contract/service/RPC already satisfies the backend capability, suppress new proto, database, repository, and service skeleton proposals. In that case, report the existing backend owner, caller integration impact, RBAC/public-method status, docs/inventory impact, tests, and any open questions.
- For app or AI integration requests, prefer output about existing backend owner, app callers, AI tool profiles, permissions, inventories, and verification. Do not create a new backend service proposal unless the user explicitly asks for a new service or no existing owner is found.

Produce a services-focused plan that a backend developer could implement in a follow-up step.
