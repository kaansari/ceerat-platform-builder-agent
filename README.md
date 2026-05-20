# Ceerat Service Builder Agent

Developer CLI agent for planning Ceerat backend service capabilities.

This tool reads Ceerat architecture context from `.ceerat-agent/`, sends a module
request to OpenAI, and prints a structured implementation plan. For now it only
produces plans; it does not generate code, modify external repositories, or run
git commands.

The agent is intentionally scoped to backend service work:

- protobuf/gRPC contracts
- backend service handlers and repositories
- PostgreSQL OLTP database objects and migrations
- JWT/RBAC/security and ownership checks
- admin HTTP hooks owned by services
- structured logging and business events
- infra/config impact for service processes

It does not design frontend pages, templates, CSS, browser behavior, or AI chat UI.
Frontend and UX work should be handled by a separate UI-focused agent. This service
agent may still report integration impact for existing apps or AI tools when a
service/API change requires follow-up coordination.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

```bash
export OPENAI_API_KEY="sk-your-key"
export OPENAI_MODEL="gpt-4.1-mini"
```

`OPENAI_MODEL` is optional and defaults to `gpt-4.1-mini`.

## Usage

```bash
ceerat-builder plan "create invoice module with customer relation and line items"
```

The output includes:

- module name
- business objects
- required protos
- required services
- required database migrations
- required RBAC permissions
- required logging/events
- integration impact
- required tests
- risks/questions
