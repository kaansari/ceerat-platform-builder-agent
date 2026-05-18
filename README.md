# Ceerat Platform Builder Agent

Developer CLI agent for planning Ceerat platform modules.

This tool reads Ceerat architecture context from `.ceerat-agent/`, sends a module
request to OpenAI, and prints a structured implementation plan. For now it only
produces plans; it does not generate code, modify external repositories, or run
git commands.

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
- required UI pages
- required RBAC permissions
- required AI agent tools
- required tests
- risks/questions
