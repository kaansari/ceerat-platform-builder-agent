Create the initial Ceerat Service Builder Agent project in Python.

This is a developer CLI agent, not part of the runtime Ceerat web app.

Use:
- Python 3.11+
- Typer for CLI
- OpenAI Python SDK for optional cloud AI planning mode
- Pydantic for structured models
- PyYAML for future specs
- Jinja2 for future templates
- Rich for terminal output

Create this structure:

ceerat-platform-builder-agent/
  pyproject.toml
  README.md
  ceerat_builder/
    __init__.py
    main.py
    config.py
    context_loader.py
    planner.py
    openai_client.py
    models.py
  .ceerat-agent/
    architecture.md
    module-generation-standard.md
    service-standards.md
    security-rbac-standard.md
    prompts/
      system.md
      planner.md
  examples/
    invoice-request.txt

Create a CLI command:

ceerat-builder plan "create invoice module"

The command should:
1. Load Ceerat architecture docs from .ceerat-agent/
2. Load system and planner prompts
3. Load contract, service, and app inventories
4. Build a local structured implementation plan for Codex by default
5. Print a structured implementation plan using Rich or JSON
6. Support optional `--mode ai`, which calls OpenAI and requires OPENAI_API_KEY

Also support tool-friendly commands:

- `ceerat-builder plan --output json "<request>"`
- `ceerat-builder plan --mode local --output json "<request>"`
- `ceerat-builder plan --mode ai --output json "<request>"`
- `ceerat-builder plan --output json --output-file <path> "<request>"`
- `ceerat-builder schema`
- `ceerat-builder check-context`
- `ceerat-builder inventory`
- `ceerat-builder inventory --output json`

For now:
- do not generate code
- do not modify external repos
- do not run git commands
- only produce a plan

Add clean error handling for:
- missing architecture docs
- missing inventory files
- missing OPENAI_API_KEY only when `--mode ai`
- OpenAI API failure only when `--mode ai`

README should include:

python -m venv .venv
source .venv/bin/activate
pip install -e .

ceerat-builder plan "create invoice module with customer relation and line items"

The output should include:
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

The agent should focus on backend services only: contracts, service handlers,
repositories, database objects, security/RBAC, logging/events, and service
infra/config. It should not design frontend pages, templates, CSS, browser
interactions, or AI chat UI.
