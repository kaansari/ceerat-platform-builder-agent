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

Codex/tool-friendly JSON output:

```bash
ceerat-builder plan --output json "create invoice service with customer relation and line items"
```

Write the plan to a file:

```bash
ceerat-builder plan --output json \
  --output-file /tmp/ceerat-builder-runs/invoice-plan.json \
  "create invoice service with customer relation and line items"
```

Inspect the strict JSON schema without calling OpenAI:

```bash
ceerat-builder schema
```

Validate that the builder context loads:

```bash
ceerat-builder check-context
```

Inspect the repo inventories without calling OpenAI:

```bash
ceerat-builder inventory
ceerat-builder inventory --output json
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

## Codex Tool Workflow

The builder is meant to be a tool that Codex can call before implementing backend
services:

```text
User asks Codex for a service
  -> Codex runs ceerat-builder inventory
  -> Codex runs ceerat-builder plan --output json "<request>"
  -> Codex reads the structured plan
  -> Codex implements in a temp workspace or explicit approved target
  -> Codex runs tests/builds
  -> User reviews and approves before real repo changes are merged
```

The builder does not apply code changes by itself. It gives Codex a consistent
Ceerat-specific service plan and inventory context so the implementation starts
from the platform standards instead of a fresh reread of every repository.
