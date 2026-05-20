Create a structured implementation plan for the requested Ceerat module.

Use the loaded `.ceerat-agent` context and current platform patterns.

The plan must include:

- `module_name`: clear human-readable module name.
- `business_objects`: domain objects, relationships, ownership, statuses, and BI/business events.
- `required_protos`: protobuf messages, gRPC services/RPCs, full gRPC method names, contract/domain/mapper changes, and proto regeneration notes.
- `required_services`: backend ownership decision, handlers, repositories, startup wiring, admin HTTP hooks if needed, logging, infra/startup/config changes.
- `required_database_migrations`: OLTP tables, indexes, constraints, seed data, transactions, and separate BI/analytics tables if needed.
- `required_ui_pages`: admin/web/customer UI pages, same-origin app endpoints, states, validation, permissions, and workflows.
- `required_rbac_permissions`: exact gRPC methods for `KnownGRPCMethods`, default role permissions, public methods if any, admin-only requirements, and ownership checks.
- `required_ai_agent_tools`: read/mutation tools, schemas, backend APIs used, permission checks, business events, and audit behavior.
- `required_tests`: contract, service, repository, security/RBAC, ownership, admin API, UI, AI tool, logging/event, and infra tests.
- `risks_questions`: missing product decisions, ambiguous ownership, migration risks, security concerns, UI uncertainties, BI/event open questions.

Planning rules:

- Do not generate code.
- Do not modify external repositories.
- Do not run git commands.
- Do not propose direct app or agent database writes.
- Do not put persistence details in contracts.
- Keep public APIs minimal.
- Keep customer-owned data scoped to authenticated user identity.
- Include infra/log/config changes when a new process, port, environment variable, or log file is needed.
- Include BI/intelligence events for meaningful business behavior, using a separate analytics store rather than raw logs.

Produce a plan that a developer could implement in a follow-up step.

