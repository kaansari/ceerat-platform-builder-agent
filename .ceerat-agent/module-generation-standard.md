# Module Generation Standard

Every module plan should describe:

- The module name and business purpose.
- Primary business objects and relationships.
- Protobuf messages, service RPCs, and external contracts.
- Service responsibilities and integration points.
- Database migrations, indexes, constraints, and seed data.
- UI pages needed for normal operator workflows.
- RBAC permissions and role assignments.
- AI agent tools required to read or mutate module data.
- Unit, integration, contract, migration, UI, and agent-tool tests.

Plans should call out risks, missing product decisions, and ambiguous data model
choices.
