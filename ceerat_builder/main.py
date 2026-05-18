from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ceerat_builder.config import ConfigError, load_settings
from ceerat_builder.context_loader import ContextError, load_agent_context
from ceerat_builder.models import ImplementationPlan
from ceerat_builder.openai_client import CeeratOpenAIClient, OpenAIClientError
from ceerat_builder.planner import build_plan

app = typer.Typer(help="Ceerat Platform Builder Agent CLI.")
console = Console()


@app.callback()
def cli() -> None:
    """Ceerat Platform Builder Agent CLI."""


def _add_rows(table: Table, title: str, values: list[str]) -> None:
    rendered = "\n".join(f"- {value}" for value in values) if values else "None"
    table.add_row(title, rendered)


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
    _add_rows(table, "UI pages", plan.required_ui_pages)
    _add_rows(table, "RBAC permissions", plan.required_rbac_permissions)
    _add_rows(table, "AI agent tools", plan.required_ai_agent_tools)
    _add_rows(table, "Tests", plan.required_tests)
    _add_rows(table, "Risks/questions", plan.risks_questions)

    console.print(table)


@app.command()
def plan(
    request: Annotated[
        str,
        typer.Argument(help='Module request, such as "create invoice module".'),
    ],
) -> None:
    """Create a structured implementation plan. This command does not generate code."""
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
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    render_plan(implementation_plan)


if __name__ == "__main__":
    app()
