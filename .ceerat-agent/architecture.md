# Ceerat Architecture

Ceerat is a modular platform composed of domain services, protobuf contracts,
database-backed storage, web UI surfaces, and AI agent tools. New modules should
fit into the existing platform boundaries and expose clear contracts between the
API, service, data, UI, and agent layers.

Modules should be planned before implementation. The builder agent must identify
domain objects, service ownership, persistence needs, UI workflows, permissions,
agent tools, and test coverage before any code is generated.
