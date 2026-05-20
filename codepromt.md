Create the initial Ceerat Service Builder Agent project in Python.

This is a developer CLI agent, not part of the runtime Ceerat web app.

Use:
- Python 3.11+
- Typer for CLI
- OpenAI Python SDK
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
3. Read OPENAI_API_KEY from environment
4. Read OPENAI_MODEL from environment, default to gpt-4.1-mini
5. Send the user request plus Ceerat context to OpenAI
6. Print a structured implementation plan using Rich

Also support tool-friendly commands:

- `ceerat-builder plan --output json "<request>"`
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
- missing OPENAI_API_KEY
- missing architecture docs
- OpenAI API failure

README should include:

python -m venv .venv
source .venv/bin/activate
pip install -e .

export OPENAI_API_KEY="sk-your-key"
export OPENAI_MODEL="gpt-4.1-mini"

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
