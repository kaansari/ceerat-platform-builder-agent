from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ceerat_builder.config import ConfigError, load_ai_settings
from ceerat_builder.context_loader import ContextError, load_agent_context
from ceerat_builder.models import ImplementationPlan
from ceerat_builder.openai_client import CeeratOpenAIClient, OpenAIClientError
from ceerat_builder.planner import build_ai_plan

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


def _words(value: str) -> List[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return [word for word in cleaned.split() if word]


def _request_terms(value: str) -> List[str]:
    ignored = {
        "a",
        "an",
        "and",
        "build",
        "create",
        "for",
        "me",
        "module",
        "new",
        "service",
        "the",
        "with",
    }
    return [word for word in _words(value) if word not in ignored]


def _domain_name(request: str) -> str:
    words = _request_terms(request)
    if not words:
        return "Requested"
    return " ".join(word.capitalize() for word in words[:3])


def _matching_contracts(inventories: Dict[str, Any], request: str) -> List[str]:
    request_words = set(_request_terms(request))
    matches: List[str] = []
    for package in inventories["contracts"].get("proto_packages", []):
        haystack = set(_words(" ".join([
            package.get("package", ""),
            package.get("service", {}).get("full_service", ""),
            package.get("service", {}).get("domain", ""),
        ])))
        if request_words & haystack:
            matches.append(package.get("service", {}).get("full_service", package.get("package", "")))
    return matches


def _matching_services(inventories: Dict[str, Any], request: str) -> List[str]:
    request_words = set(_request_terms(request))
    matches: List[str] = []
    for service in inventories["services"].get("grpc_services", []):
        haystack = set(_words(" ".join([
            service.get("full_service", ""),
            service.get("domain", ""),
            service.get("owner_project", ""),
        ])))
        if request_words & haystack:
            matches.append(service.get("full_service", ""))
    return matches


def _local_plan(request: str, project_root: Path) -> ImplementationPlan:
    # Loading context here validates the builder setup even though the local planner
    # does not send that context to an external model.
    load_agent_context(project_root)
    inventories = _load_inventories(project_root)
    domain = _domain_name(request)
    module_name = f"{domain} Service"
    contract_matches = _matching_contracts(inventories, request)
    service_matches = _matching_services(inventories, request)

    if contract_matches or service_matches:
        ownership_note = (
            "Inventory match found: "
            + ", ".join(sorted(set(contract_matches + service_matches)))
            + ". Codex should extend the existing owner when the requested behavior belongs there."
        )
    else:
        ownership_note = (
            "No direct inventory match found. Codex should decide whether this is a new service boundary "
            "or a new module inside ceerat-user-service before writing code."
        )

    proto_package = domain.lower().replace(" ", "_").replace("-", "_")
    method_prefix = "".join(part.capitalize() for part in proto_package.split("_"))

    return ImplementationPlan(
        module_name=module_name,
        business_objects=[
            f"User request: {request}",
            ownership_note,
            "Codex must identify core domain objects, relationships, ownership, lifecycle statuses, and business events before implementation.",
            "Customer-owned or user-owned data must be scoped to the authenticated user in handlers and repositories.",
        ],
        required_protos=[
            "Check contracts-repo/docs/contract-inventory.json before adding a proto package, message, or RPC.",
            f"If this is a new boundary, consider proto package `{proto_package}` with a `{method_prefix}Manager` or domain-specific gRPC service.",
            "If an existing package owns the domain, extend that package instead of creating a duplicate.",
            "Add request/response messages, regenerate protobuf Go code with `make proto`, and keep contracts free of GORM/database concerns.",
            "For every protected RPC, add the exact full method to KnownGRPCMethods and default role permissions.",
        ],
        required_services=[
            "Check services-repo/docs/grpc-service-inventory.json before creating a new backend service.",
            "Prefer extending ceerat-user-service unless the domain has independent ownership, scaling, security, or persistence lifecycle needs.",
            "Implement generated gRPC handlers plus repository methods following the existing handler.go/repository.go/handler_test.go pattern.",
            "Wire startup with config, structured logger, DB connection, migrations/seed, repositories, JWT/RBAC interceptors, service registration, reflection, and optional admin HTTP hooks.",
            "Add admin HTTP endpoints only for service-owned operational management and protect them with admin-only auth.",
        ],
        required_database_migrations=[
            "Define OLTP tables/entities, primary keys, foreign keys, unique constraints, indexes, and status values.",
            "Use repository-level ownership scoping for customer/user-owned reads and writes.",
            "Use transactions for multi-table writes and snapshot mutable catalog data when historical accuracy matters.",
            "Add idempotent seed data only when required.",
            "Send reporting/intelligence data to a separate BI/event store when needed; do not use raw logs as reporting storage.",
        ],
        required_rbac_permissions=[
            "Use JWT -> RBAC -> Logging -> Handler interceptor order for protected unary gRPC calls.",
            "Keep DefaultPublicMethods minimal; public methods should normally be login, registration, token validation, or health only.",
            "Add new protected full gRPC methods to KnownGRPCMethods.",
            "Update DefaultRolePermissions for admin, agent, customer, or new roles as appropriate.",
            "Handlers must read AuthenticatedUserFromContext and enforce record ownership beyond method-level RBAC.",
        ],
        required_logging_events=[
            "Use structured slog logs with stable service/env context.",
            "Log grpc_method, status, duration_ms, and error for gRPC calls.",
            "Redact fields containing password, token, secret, or key.",
            "Add business events for meaningful mutations, such as created/updated/status_changed/assigned, suitable for future BI ingestion.",
            "Analytics/event failures must not roll back primary OLTP transactions unless explicitly required.",
        ],
        integration_impact=[
            "Check apps-repo/docs/app-surface-inventory.json only for caller compatibility; do not design frontend UI in this builder.",
            "If contracts change, identify existing app, admin, customer, or AI callers that need follow-up work by another agent.",
            "If a new process is introduced, note infra start/stop/log/env updates required in infra.",
            "If AI tools should use the new service later, note the backend RPCs and permissions they would call, but do not implement AI tool/UI behavior here.",
        ],
        required_tests=[
            "Contract generation/build tests.",
            "Handler tests for valid requests, invalid arguments, backend errors, and domain edge cases.",
            "Repository tests for ownership scoping, constraints, transactions, and not-found behavior.",
            "Security tests for missing token, invalid token, RBAC denied, RBAC allowed, and cross-user access denied.",
            "Admin HTTP tests if admin hooks are added.",
            "Logging/redaction and business event tests for important mutations.",
        ],
        risks_questions=[
            "Confirm whether this belongs in ceerat-user-service or a new backend service.",
            "Confirm authenticated ownership model and role permissions before implementation.",
            "Confirm required statuses, uniqueness rules, deletion/archival behavior, and seed data.",
            "Confirm whether any existing app or AI caller needs coordinated follow-up.",
            "Confirm BI/event requirements if this service creates executive reporting or recommendations later.",
        ],
    )


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
    mode: str = typer.Option(
        "local",
        "--mode",
        help="Planning mode: local or ai. Local does not call OpenAI; ai requires OPENAI_API_KEY.",
    ),
) -> None:
    """Create a structured service implementation plan. This command does not generate code."""
    output = output.lower().strip()
    mode = mode.lower().strip()
    if output not in {"table", "json"}:
        error_console.print("[bold red]Error:[/bold red] --output must be table or json")
        raise typer.Exit(code=2)
    if mode not in {"local", "ai"}:
        error_console.print("[bold red]Error:[/bold red] --mode must be local or ai")
        raise typer.Exit(code=2)
    if output_file is not None and output != "json":
        error_console.print("[bold red]Error:[/bold red] --output-file is only supported with --output json")
        raise typer.Exit(code=2)

    try:
        if mode == "ai":
            settings = load_ai_settings(Path(".").resolve())
            context = load_agent_context(settings.project_root)
            client = CeeratOpenAIClient(api_key=settings.api_key, model=settings.model)
            implementation_plan = build_ai_plan(
                client=client,
                context=context,
                user_request=request,
            )
        else:
            implementation_plan = _local_plan(request, Path(".").resolve())
    except (ConfigError, ContextError, OpenAIClientError, json.JSONDecodeError) as exc:
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
