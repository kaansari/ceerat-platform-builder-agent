from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ceerat_builder.config import ConfigError, load_settings
from ceerat_builder.context_loader import ContextError, load_agent_context
from ceerat_builder.models import ImplementationPlan
from ceerat_builder.openai_client import CeeratOpenAIClient, OpenAIClientError
from ceerat_builder.planner import build_plan

app = typer.Typer(help="Ceerat Service Builder Agent CLI.")
console = Console()
error_console = Console(stderr=True)


@app.callback()
def cli() -> None:
    """Ceerat Service Builder Agent CLI."""


def _add_rows(table: Table, title: str, values: List[str]) -> None:
    rendered = "\n".join(f"- {value}" for value in values) if values else "None"
    table.add_row(title, rendered)


def _plan_json(plan: ImplementationPlan) -> str:
    return plan.model_dump_json(indent=2)


def _write_output(payload: str, output_file: Optional[Path]) -> None:
    if output_file is None:
        print(payload)
        return
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(payload + "\n", encoding="utf-8")
    console.print(f"Wrote {output_file}")


def render_plan(plan: ImplementationPlan) -> None:
    console.print(
        Panel.fit(
            f"[bold]{plan.module_name}[/bold]",
            title="Ceerat Implementation Plan",
            border_style="cyan",
        )
    )

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Area", style="bold", no_wrap=True)
    table.add_column("Plan")

    _add_rows(table, "Business objects", plan.business_objects)
    _add_rows(table, "Required protos", plan.required_protos)
    _add_rows(table, "Required services", plan.required_services)
    _add_rows(table, "Database migrations", plan.required_database_migrations)
    _add_rows(table, "RBAC permissions", plan.required_rbac_permissions)
    _add_rows(table, "Logging/events", plan.required_logging_events)
    _add_rows(table, "Integration impact", plan.integration_impact)
    _add_rows(table, "Tests", plan.required_tests)
    _add_rows(table, "Risks/questions", plan.risks_questions)

    console.print(table)


@app.command()
def plan(
    request: str = typer.Argument(
        ...,
        help='Service request, such as "create invoice service".',
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table or json.",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output-file",
        help="Optional file path for JSON output.",
    ),
) -> None:
    """Create a structured service implementation plan. This command does not generate code."""
    output = output.lower().strip()
    if output not in {"table", "json"}:
        error_console.print("[bold red]Error:[/bold red] --output must be table or json")
        raise typer.Exit(code=2)
    if output_file is not None and output != "json":
        error_console.print("[bold red]Error:[/bold red] --output-file is only supported with --output json")
        raise typer.Exit(code=2)

    try:
        settings = load_settings()
        context = load_agent_context(settings.project_root)
        client = CeeratOpenAIClient(api_key=settings.api_key, model=settings.model)
        implementation_plan = build_plan(
            client=client,
            context=context,
            user_request=request,
        )
    except (ConfigError, ContextError, OpenAIClientError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if output == "json":
        _write_output(_plan_json(implementation_plan), output_file)
        return

    render_plan(implementation_plan)


def _workspace_root(project_root: Path) -> Path:
    root = project_root.resolve()
    if root.name == "ceerat-platform-builder-agent":
        return root.parent
    return root


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ContextError(f"Missing inventory file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_inventories(project_root: Path) -> Dict[str, Any]:
    workspace = _workspace_root(project_root)
    files = {
        "contracts": workspace / "contracts-repo" / "docs" / "contract-inventory.json",
        "services": workspace / "services-repo" / "docs" / "grpc-service-inventory.json",
        "apps": workspace / "apps-repo" / "docs" / "app-surface-inventory.json",
    }
    return {name: _read_json(path) for name, path in files.items()}


@app.command("inventory")
def inventory(
    output: str = typer.Option(
        "summary",
        "--output",
        "-o",
        help="Output format: summary or json.",
    ),
    project_root: Path = typer.Option(
        Path("."),
        "--project-root",
        help="Builder repo root, or workspace root containing contracts-repo/services-repo/apps-repo.",
    ),
) -> None:
    """Inspect Ceerat inventories without calling OpenAI."""
    output = output.lower().strip()
    if output not in {"summary", "json"}:
        error_console.print("[bold red]Error:[/bold red] --output must be summary or json")
        raise typer.Exit(code=2)
    try:
        inventories = _load_inventories(project_root)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if output == "json":
        print(json.dumps(inventories, indent=2, sort_keys=True))
        return

    contracts = inventories["contracts"]
    services = inventories["services"]
    apps = inventories["apps"]

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Inventory", style="bold")
    table.add_column("Counts")

    table.add_row(
        "Contracts",
        "\n".join(
            [
                f"proto packages: {len(contracts.get('proto_packages', []))}",
                f"rpc methods: {sum(len(p.get('service', {}).get('rpcs', [])) for p in contracts.get('proto_packages', []))}",
                f"messages: {sum(len(p.get('messages', [])) for p in contracts.get('proto_packages', []))}",
                f"domain models: {len(contracts.get('domain_models', []))}",
            ]
        ),
    )
    table.add_row(
        "Services",
        "\n".join(
            [
                f"backend projects: {len(services.get('backend_services', []))}",
                f"grpc services: {len(services.get('grpc_services', []))}",
                f"rpc methods: {sum(len(s.get('methods', [])) for s in services.get('grpc_services', []))}",
            ]
        ),
    )
    table.add_row(
        "Apps",
        "\n".join(
            [
                f"browser apps: {len(apps.get('browser_apps', []))}",
                f"ai apps: {len(apps.get('ai_apps', []))}",
                f"handlers: {sum(len(a.get('handlers', [])) for a in apps.get('browser_apps', [])) + sum(len(a.get('handlers', [])) for a in apps.get('ai_apps', []))}",
            ]
        ),
    )
    console.print(table)


@app.command("schema")
def schema() -> None:
    """Print the strict JSON schema Codex should expect from plan --output json."""
    print(json.dumps(ImplementationPlan.model_json_schema(), indent=2, sort_keys=True))


@app.command("check-context")
def check_context(
    project_root: Path = typer.Option(
        Path("."),
        "--project-root",
        help="Builder repo root containing .ceerat-agent.",
    )
) -> None:
    """Validate that required builder context files can be loaded."""
    try:
        context = load_agent_context(project_root.resolve())
    except ContextError as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    print(
        json.dumps(
            {
                "ok": True,
                "architecture_context_bytes": len(context.architecture_context),
                "system_prompt_bytes": len(context.system_prompt),
                "planner_prompt_bytes": len(context.planner_prompt),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
