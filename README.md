# Ceerat Service Builder Agent

Developer CLI agent for planning Ceerat backend service capabilities.

This tool reads Ceerat architecture context and repository inventories, then
prints structured JSON for service work. It has two planning modes:

- `local`: default mode for Codex. Does not call OpenAI or require an API key. Returns a planning packet for Codex to reason over.
- `ai`: future cloud mode. Calls OpenAI and requires `OPENAI_API_KEY`. Returns a full implementation plan.

The builder does not generate code, modify external repositories, or run git
commands.

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

## Usage

```bash
ceerat-builder plan "create invoice module with customer relation and line items"
```

The default is local mode:

```bash
ceerat-builder plan --mode local "create invoice service"
```

Codex/tool-friendly JSON output:

```bash
ceerat-builder plan --output json "create invoice service with customer relation and line items"
```

In local mode, this JSON is a planning packet, not the final service design.
It contains the request, inventory matches, extracted related contracts,
recommended owner, domain requirements, concrete source evidence, suggested
contract/RPC skeletons, suggested database objects, suggested service files,
suggested RBAC permissions, relevant standards/docs, caller compatibility
context, and explicit instructions for Codex.

Domain requirements can be kept in `.ceerat-agent/domain-requirements.json`.
Use this file for must-have business fields and relationships that should not be
lost during planning. For example, the invoice entry states that one order can
have many invoices, so the builder tells Codex to use `invoices.order_id ->
orders.id`, add an index, and avoid a unique constraint on `order_id`.

You can also pass a different requirements file:

```bash
ceerat-builder plan --output json \
  --requirements-file /tmp/invoice-requirements.json \
  "create invoice service"
```

Future cloud/AI mode:

```bash
export OPENAI_API_KEY="sk-your-key"
export OPENAI_MODEL="gpt-4.1-mini"

ceerat-builder plan --mode ai --output json "create invoice service"
```

`OPENAI_API_KEY` is required only for `--mode ai`.

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

Local packet output includes:

- original request
- Codex task
- inventory matches
- detected domain
- recommended owner
- related contract summaries
- domain requirements from request text and `.ceerat-agent/domain-requirements.json`
- source evidence from current service, contract, security, logging, and docs files
- suggested contract/RPC skeleton
- suggested database objects
- suggested service skeleton
- suggested RBAC permissions
- relevant contracts
- relevant services
- database context
- security context
- app/caller compatibility context
- standards to apply
- required output from Codex
- warnings

AI mode plan output includes:

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

The builder is meant to be a local tool that Codex can call before implementing
backend services:

```text
User asks Codex for a service
  -> Codex runs ceerat-builder inventory
  -> Codex runs ceerat-builder plan --mode local --output json "<request>"
  -> Codex reads the planning packet
  -> Codex produces the actual service plan or implementation
  -> Codex implements in a temp workspace or explicit approved target
  -> Codex runs tests/builds
  -> User reviews and approves before real repo changes are merged
```

The builder does not apply code changes by itself. It gives Codex a consistent
Ceerat-specific service plan and inventory context so the implementation starts
from the platform standards instead of a fresh reread of every repository. In
local mode, Codex does the reasoning and implementation. In cloud AI mode, the
builder can ask OpenAI for the service plan when Codex is not available.
