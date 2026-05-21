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
from ceerat_builder.models import (
    DomainRequirement,
    ImplementationPlan,
    InventoryMatch,
    PlanningPacket,
    RecommendedOwner,
    RelatedContract,
    SourceEvidence,
    SuggestedContract,
    SuggestedDatabaseObject,
    SuggestedRBACPermission,
    SuggestedRPC,
    SuggestedServiceSkeleton,
)
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


def _packet_json(packet: PlanningPacket) -> str:
    return packet.model_dump_json(indent=2)


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


def render_packet(packet: PlanningPacket) -> None:
    console.print(
        Panel.fit(
            f"[bold]{packet.request}[/bold]",
            title="Ceerat Planning Packet",
            border_style="green",
        )
    )

    table = Table(show_header=True, header_style="bold green")
    table.add_column("Area", style="bold", no_wrap=True)
    table.add_column("Packet")

    _add_rows(table, "Codex task", [packet.codex_task])
    _add_rows(table, "Detected domain", [packet.detected_domain])
    _add_rows(table, "Recommended owner", [f"{packet.recommended_owner.service_project}: {packet.recommended_owner.reason}"])
    _add_rows(table, "Inventory matches", [f"{m.source}: {m.name} ({m.reason})" for m in packet.inventory_matches])
    _add_rows(table, "Related contracts", [f"{c.service}: {', '.join(c.rpcs)}" for c in packet.related_contracts])
    _add_rows(table, "Domain requirements", [f"{r.category}: {r.requirement}" for r in packet.domain_requirements])
    _add_rows(table, "Source evidence", [f"{e.category}: {e.path} ({e.finding})" for e in packet.source_evidence])
    _add_rows(table, "Suggested contract", [f"{packet.suggested_contract.package}.{packet.suggested_contract.service}"])
    _add_rows(table, "Suggested DB", [obj.name for obj in packet.suggested_database_objects])
    _add_rows(table, "Suggested service", packet.suggested_service_skeleton.files)
    _add_rows(table, "Suggested RBAC", [perm.method for perm in packet.suggested_rbac_permissions])
    _add_rows(table, "Relevant contracts", packet.relevant_contracts)
    _add_rows(table, "Relevant services", packet.relevant_services)
    _add_rows(table, "Database", packet.relevant_database)
    _add_rows(table, "Security", packet.relevant_security)
    _add_rows(table, "Apps/callers", packet.relevant_apps_or_callers)
    _add_rows(table, "Standards", packet.standards_to_apply)
    _add_rows(table, "Codex output", packet.required_output_from_codex)
    _add_rows(table, "Warnings", packet.warnings)

    console.print(table)


def _words(value: str) -> List[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return [word for word in cleaned.split() if word]


def _request_terms(value: str) -> List[str]:
    ignored = {
        "a",
        "add",
        "an",
        "and",
        "based",
        "belongs",
        "bills",
        "build",
        "can",
        "constraint",
        "create",
        "delete",
        "do",
        "does",
        "expose",
        "field",
        "fields",
        "for",
        "foreign",
        "get",
        "has",
        "have",
        "identify",
        "implementation",
        "index",
        "it",
        "its",
        "key",
        "list",
        "many",
        "me",
        "message",
        "messages",
        "module",
        "must",
        "new",
        "not",
        "one",
        "record",
        "records",
        "service",
        "the",
        "to",
        "unique",
        "update",
        "use",
        "with",
    }
    return [word for word in _words(value) if word not in ignored]


def _domain_name(request: str) -> str:
    words = _request_terms(request)
    if not words:
        return "Requested"
    return " ".join(word.capitalize() for word in words[:3])


def _domain_key(request: str) -> str:
    terms = _request_terms(request)
    return terms[0] if terms else "requested"


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


def _contract_matches(inventories: Dict[str, Any], request: str) -> List[InventoryMatch]:
    request_words = set(_request_terms(request))
    matches: List[InventoryMatch] = []
    for package in inventories["contracts"].get("proto_packages", []):
        service = package.get("service", {})
        haystack = set(_words(" ".join([
            package.get("package", ""),
            service.get("full_service", ""),
            service.get("domain", ""),
            " ".join(msg.get("name", "") for msg in package.get("messages", [])),
        ])))
        shared = sorted(request_words & haystack)
        if shared:
            matches.append(InventoryMatch(
                source="contracts",
                name=service.get("full_service", package.get("package", "")),
                path=package.get("proto_path", ""),
                reason="matched request terms: " + ", ".join(shared),
            ))
    return matches


def _service_matches(inventories: Dict[str, Any], request: str) -> List[InventoryMatch]:
    request_words = set(_request_terms(request))
    matches: List[InventoryMatch] = []
    for service in inventories["services"].get("grpc_services", []):
        haystack = set(_words(" ".join([
            service.get("full_service", ""),
            service.get("domain", ""),
            service.get("owner_project", ""),
            " ".join(method.get("name", "") for method in service.get("methods", [])),
        ])))
        shared = sorted(request_words & haystack)
        if shared:
            matches.append(InventoryMatch(
                source="services",
                name=service.get("full_service", ""),
                path=service.get("implementation_package", service.get("proto_path", "")),
                reason="matched request terms: " + ", ".join(shared),
            ))
    return matches


def _app_matches(inventories: Dict[str, Any], request: str) -> List[InventoryMatch]:
    request_words = set(_request_terms(request))
    matches: List[InventoryMatch] = []
    for app_item in inventories["apps"].get("browser_apps", []) + inventories["apps"].get("ai_apps", []):
        haystack = set(_words(" ".join([
            app_item.get("name", ""),
            app_item.get("type", ""),
            " ".join(handler.get("route", "") for handler in app_item.get("handlers", [])),
            " ".join(app_item.get("tools", [])),
        ])))
        shared = sorted(request_words & haystack)
        if shared:
            matches.append(InventoryMatch(
                source="apps",
                name=app_item.get("name", ""),
                path=app_item.get("path", ""),
                reason="caller compatibility match on terms: " + ", ".join(shared),
            ))
    return matches


def _related_domain_terms(request: str, requirements: List[DomainRequirement]) -> List[str]:
    terms = set(_request_terms(request))
    for requirement in requirements:
        terms.update(_request_terms(requirement.requirement))
        terms.update(_request_terms(requirement.implementation_hint))
        if requirement.name:
            terms.update(_request_terms(requirement.name))
    return sorted(terms)


def _find_contract_package(inventories: Dict[str, Any], package_name: str) -> Optional[Dict[str, Any]]:
    for package in inventories["contracts"].get("proto_packages", []):
        if package.get("package") == package_name:
            return package
    return None


def _related_contracts(inventories: Dict[str, Any], request: str, requirements: List[DomainRequirement]) -> List[RelatedContract]:
    related_terms = set(_related_domain_terms(request, requirements))
    contracts: List[RelatedContract] = []
    for package in inventories["contracts"].get("proto_packages", []):
        service = package.get("service", {})
        package_name = package.get("package", "")
        haystack = set(_words(" ".join([
            package_name,
            service.get("full_service", ""),
            service.get("domain", ""),
            " ".join(msg.get("name", "") for msg in package.get("messages", [])),
            " ".join(rpc.get("name", "") for rpc in service.get("rpcs", [])),
        ])))
        shared = sorted(related_terms & haystack)
        if shared:
            reason = "related terms: " + ", ".join(shared)
        else:
            reason = ""
        if reason:
            contracts.append(RelatedContract(
                package=package_name,
                service=service.get("full_service", ""),
                proto_path=package.get("proto_path", ""),
                domain=service.get("domain", ""),
                rpcs=[rpc.get("name", "") for rpc in service.get("rpcs", [])],
                messages=[msg.get("name", "") for msg in package.get("messages", [])],
                reason=reason,
            ))
    return contracts


def _recommended_owner(domain: str, related_contracts: List[RelatedContract]) -> RecommendedOwner:
    if related_contracts:
        return RecommendedOwner(
            service_project="ceerat-user-service",
            path="services-repo/services/ceerat-user-service",
            recommendation="extend_existing_service",
            reason="Related contracts are currently implemented by ceerat-user-service.",
        )
    return RecommendedOwner(
        service_project="new-service-or-ceerat-user-service-module",
        path="services-repo/services",
        recommendation="requires_codex_decision",
        reason="No strong inventory owner was found. Codex should decide whether to create a new service or extend ceerat-user-service.",
    )


def _pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


def _suggested_contract(domain: str) -> SuggestedContract:
    pascal = _pascal(domain)
    package = domain.replace("-", "_")
    rpcs = [
        SuggestedRPC(name=f"Create{pascal}", full_method=f"/{package}.{pascal}Manager/Create{pascal}", request=f"Create{pascal}Request", response=f"{pascal}Response", purpose=f"Create a {domain} record."),
        SuggestedRPC(name=f"Get{pascal}", full_method=f"/{package}.{pascal}Manager/Get{pascal}", request=f"Get{pascal}Request", response=f"{pascal}Response", purpose=f"Get one {domain} record."),
        SuggestedRPC(name=f"List{pascal}s", full_method=f"/{package}.{pascal}Manager/List{pascal}s", request=f"List{pascal}sRequest", response=f"List{pascal}sResponse", purpose=f"List {domain} records."),
        SuggestedRPC(name=f"Update{pascal}", full_method=f"/{package}.{pascal}Manager/Update{pascal}", request=f"Update{pascal}Request", response=f"{pascal}Response", purpose=f"Update a {domain} record."),
    ]
    messages = [
        pascal,
        f"Create{pascal}Request",
        f"Get{pascal}Request",
        f"List{pascal}sRequest",
        f"Update{pascal}Request",
        f"{pascal}Response",
        f"List{pascal}sResponse",
        "Error",
    ]
    return SuggestedContract(
        package=package,
        service=f"{pascal}Manager",
        proto_path=f"packages/ceerat-contracts/proto/{package}/{package}.proto",
        rpcs=rpcs,
        messages=messages,
    )


def _suggested_database_objects(domain: str, requirements: List[DomainRequirement]) -> List[SuggestedDatabaseObject]:
    table = f"{domain}s"
    field_names = [requirement.name for requirement in requirements if requirement.category == "field" and requirement.name]
    relationship_hints = [
        requirement.implementation_hint or requirement.requirement
        for requirement in requirements
        if requirement.category == "relationship"
    ]
    key_columns = ["id"] + field_names + ["created_at", "updated_at"]
    indexes = [f"index({field})" for field in field_names if field.endswith("_id")]
    if not indexes:
        indexes = ["add indexes based on repository query filters"]
    return [
        SuggestedDatabaseObject(
            name=table,
            purpose=f"{domain.capitalize()} records based on explicit requirements and existing service patterns.",
            key_columns=key_columns,
            relationships=relationship_hints,
            indexes=indexes,
        )
    ]


def _suggested_service_skeleton(domain: str, owner: RecommendedOwner) -> SuggestedServiceSkeleton:
    package = domain.replace("-", "_")
    if owner.recommendation == "extend_existing_service":
        base = "services-repo/services/ceerat-user-service"
        service_package = package + "s"
        return SuggestedServiceSkeleton(
            owner_project=owner.service_project,
            packages=[f"{base}/{service_package}", f"{base}/internal/models"],
            files=[
                f"{base}/{service_package}/handler.go",
                f"{base}/{service_package}/repository.go",
                f"{base}/{service_package}/handler_test.go",
                f"{base}/internal/models/models.go",
                f"{base}/main.go",
                "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            ],
            startup_wiring=[
                f"Create {domain} repository after DB/migrations.",
                f"Register generated { _pascal(domain) }Manager gRPC server.",
                f"Ensure JWT/RBAC/logging interceptors protect {domain} RPCs.",
                "Enable reflection as existing service already does.",
            ],
        )
    return SuggestedServiceSkeleton(
        owner_project=owner.service_project,
        packages=[f"services-repo/services/ceerat-{package}-service"],
        files=[
            f"services-repo/services/ceerat-{package}-service/main.go",
            f"services-repo/services/ceerat-{package}-service/{package}s/handler.go",
            f"services-repo/services/ceerat-{package}-service/{package}s/repository.go",
            f"services-repo/services/ceerat-{package}-service/internal/models/models.go",
        ],
        startup_wiring=[
            "Create service config/env loader.",
            "Connect to PostgreSQL.",
            "Wire JWT/RBAC/logging interceptors.",
            "Register generated gRPC server and reflection.",
            "Add infra start/stop/log integration.",
        ],
    )


def _suggested_rbac(contract: SuggestedContract, domain: str) -> List[SuggestedRBACPermission]:
    permissions: List[SuggestedRBACPermission] = []
    for rpc in contract.rpcs:
        is_read = rpc.name.startswith("Get") or rpc.name.startswith("List")
        roles = ["admin", "agent"]
        if is_read:
            roles.append("customer")
        permissions.append(SuggestedRBACPermission(
            method=rpc.full_method,
            default_roles=roles,
            public=False,
            ownership_rule="Scope customer/user-owned records through authenticated user before returning or mutating records. Apply domain requirements for relationship-specific ownership.",
        ))
    return permissions


def _default_requirements_path(project_root: Path) -> Path:
    return project_root / ".ceerat-agent" / "domain-requirements.json"


def _load_domain_requirements(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _configured_domain_requirements(domain: str, path: Optional[Path]) -> List[DomainRequirement]:
    data = _load_domain_requirements(path)
    domain_data = data.get("domains", {}).get(domain, {})
    requirements: List[DomainRequirement] = []

    for item in domain_data.get("must_have_fields", []):
        requirements.append(DomainRequirement(
            source=str(path),
            category="field",
            name=item.get("name"),
            requirement=item.get("requirement", item.get("name", "")),
            implementation_hint=item.get("implementation_hint", ""),
        ))
    for item in domain_data.get("must_have_relationships", []):
        requirements.append(DomainRequirement(
            source=str(path),
            category="relationship",
            name=item.get("name"),
            requirement=item.get("requirement", item.get("name", "")),
            implementation_hint=item.get("implementation_hint", ""),
        ))
    for item in domain_data.get("business_rules", []):
        requirements.append(DomainRequirement(
            source=str(path),
            category="rule",
            name=item.get("name"),
            requirement=item.get("requirement", ""),
            implementation_hint=item.get("implementation_hint", ""),
        ))
    for item in domain_data.get("workflow_rules", []):
        requirements.append(DomainRequirement(
            source=str(path),
            category="workflow",
            name=item.get("name"),
            requirement=item.get("requirement", ""),
            implementation_hint=item.get("implementation_hint", ""),
        ))

    return requirements


def _request_domain_requirements(domain: str, request: str) -> List[DomainRequirement]:
    return []


def _domain_requirements(domain: str, request: str, requirements_path: Optional[Path]) -> List[DomainRequirement]:
    configured = _configured_domain_requirements(domain, requirements_path)
    requested = _request_domain_requirements(domain, request)
    seen = set()
    merged: List[DomainRequirement] = []
    for requirement in configured + requested:
        key = (requirement.category, requirement.requirement.lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(requirement)
    return merged


def _source_file_exists(workspace: Path, relative_path: str) -> bool:
    return (workspace / relative_path).is_file()


def _source_evidence(project_root: Path, owner: RecommendedOwner, related_contracts: List[RelatedContract]) -> List[SourceEvidence]:
    workspace = _workspace_root(project_root)
    evidence: List[SourceEvidence] = []

    service_main = "services-repo/services/ceerat-user-service/main.go"
    if owner.service_project == "ceerat-user-service" and _source_file_exists(workspace, service_main):
        evidence.append(SourceEvidence(
            category="service_wiring",
            path=service_main,
            symbols=[
                "createConnection",
                "db.AutoMigrate",
                "seedRBAC",
                "grpc.NewServer",
                "RegisterAuthServer",
                "RegisterCustomerServiceServer",
                "RegisterServiceManagerServer",
                "RegisterOrderManagerServer",
                "reflection.Register",
            ],
            finding=(
                "ceerat-user-service owns DB connection, AutoMigrate, seed hooks, repository construction, "
                "gRPC server creation, generated server registration, and reflection."
            ),
        ))
        evidence.append(SourceEvidence(
            category="security_wiring",
            path=service_main,
            symbols=[
                "security.NewJWTInterceptor",
                "security.NewRBACInterceptor",
                "grpcLoggingInterceptor",
                "grpc.ChainUnaryInterceptor",
                "startRBACRefresh",
                "startAdminHTTPServer",
            ],
            finding=(
                "When JWT auth is enabled, unary interceptors are chained as JWT, RBAC, then logging; "
                "RBAC cache refresh and service admin HTTP hooks are started from main."
            ),
        ))

    for relative_path, symbols, finding in [
        (
            "services-repo/services/ceerat-user-service/orders/handler.go",
            ["NewService", "CreateOrder", "GetOrder", "ListOrders", "UpdateOrderStatus"],
            "Existing domain modules use a package-level service/handler around a repository and generated protobuf server interface.",
        ),
        (
            "services-repo/services/ceerat-user-service/orders/repository.go",
            ["NewRepository", "CreateOrder", "GetOrder", "ListOrders", "UpdateOrderStatus"],
            "Order persistence is repository-owned and is the closest existing pattern for order-adjacent ownership, transactions, and line items.",
        ),
        (
            "services-repo/services/ceerat-user-service/orders/handler_test.go",
            ["Test", "bufconn", "metadata"],
            "Existing handler tests are the closest test pattern for new order-adjacent gRPC behavior.",
        ),
        (
            "services-repo/services/ceerat-user-service/internal/models/models.go",
            ["UserEntity", "CustomerEntity", "ServiceEntity", "OrderEntity", "OrderServiceEntity"],
            "GORM entities live in internal/models and are migrated from ceerat-user-service main.",
        ),
        (
            "services-repo/services/ceerat-user-service/logging.go",
            ["grpcLoggingInterceptor", "status.Code", "peer.FromContext"],
            "Structured gRPC logs are centralized in the service logging interceptor.",
        ),
        (
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            ["KnownGRPCMethods", "DefaultRolePermissions"],
            "New protected gRPC methods must be added to known methods and default role permissions.",
        ),
        (
            "contracts-repo/packages/ceerat-contracts/security/allowlist.go",
            ["DefaultPublicMethods"],
            "Public methods are controlled separately and should stay minimal.",
        ),
        (
            "services-repo/services/ceerat-user-service/docs/new-service-cookbook.md",
            ["service cookbook"],
            "The service cookbook is the documented implementation pattern for new service modules.",
        ),
    ]:
        if _source_file_exists(workspace, relative_path):
            evidence.append(SourceEvidence(category="source_pattern", path=relative_path, symbols=symbols, finding=finding))

    for contract in related_contracts:
        if contract.proto_path:
            evidence.append(SourceEvidence(
                category="contract_inventory",
                path=contract.proto_path,
                symbols=[contract.service] + contract.rpcs,
                finding=f"Related contract from inventory: {contract.domain}",
            ))

    return evidence


def _local_packet(request: str, project_root: Path, requirements_file: Optional[Path] = None) -> PlanningPacket:
    load_agent_context(project_root)
    inventories = _load_inventories(project_root)
    domain = _domain_key(request)
    matches = (
        _contract_matches(inventories, request)
        + _service_matches(inventories, request)
        + _app_matches(inventories, request)
    )
    resolved_requirements_file = requirements_file or _default_requirements_path(project_root)
    requirements = _domain_requirements(domain, request, resolved_requirements_file)
    related_contracts = _related_contracts(inventories, request, requirements)
    owner = _recommended_owner(domain, related_contracts)
    suggested_contract = _suggested_contract(domain)

    return PlanningPacket(
        request=request,
        mode="local",
        codex_task=(
            "Use this packet as context. Produce the actual service implementation plan or make code changes "
            "using Codex reasoning. Do not treat this packet as the final design."
        ),
        detected_domain=domain,
        recommended_owner=owner,
        inventory_matches=matches,
        related_contracts=related_contracts,
        domain_requirements=requirements,
        source_evidence=_source_evidence(project_root, owner, related_contracts),
        suggested_contract=suggested_contract,
        suggested_database_objects=_suggested_database_objects(domain, requirements),
        suggested_service_skeleton=_suggested_service_skeleton(domain, owner),
        suggested_rbac_permissions=_suggested_rbac(suggested_contract, domain),
        relevant_contracts=[
            "contracts-repo/docs/contract-inventory.json",
            "contracts-repo/packages/ceerat-contracts/proto",
            "contracts-repo/packages/ceerat-contracts/domain/models.go",
            "contracts-repo/packages/ceerat-contracts/mapper/mapper.go",
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            "contracts-repo/packages/ceerat-contracts/security/allowlist.go",
        ],
        relevant_services=[
            "services-repo/docs/grpc-service-inventory.json",
            "services-repo/services/ceerat-user-service",
            "services-repo/services/ceerat-user-service/docs/new-service-cookbook.md",
            "services-repo/services/ceerat-user-service/docs/api.md",
            "services-repo/services/ceerat-user-service/docs/grpc-security.md",
            "services-repo/services/ceerat-user-service/docs/logging.md",
            "services-repo/services/ceerat-user-service/docs/api-testing.md",
        ],
        relevant_database=[
            "Backend services own OLTP database schema and migrations.",
            "Apps and agents must not write directly to PostgreSQL.",
            "Use repository-level authenticated ownership scoping.",
            "Use transactions for multi-table writes.",
            "Use separate BI/event storage for analytics and intelligence workloads.",
        ],
        relevant_security=[
            "Use JWT -> RBAC -> Logging -> Handler interceptor order.",
            "Add protected RPCs to KnownGRPCMethods.",
            "Add default role permissions to DefaultRolePermissions.",
            "Keep DefaultPublicMethods minimal.",
            "Handlers must use AuthenticatedUserFromContext and enforce record ownership.",
        ],
        relevant_apps_or_callers=[
            "apps-repo/docs/app-surface-inventory.json",
            "Use app inventory only for caller compatibility.",
            "Do not design frontend pages, templates, CSS, browser JavaScript, or AI chat UI in this builder.",
        ],
        standards_to_apply=[
            "ceerat-platform-builder-agent/.ceerat-agent/architecture.md",
            "ceerat-platform-builder-agent/.ceerat-agent/module-generation-standard.md",
            "ceerat-platform-builder-agent/.ceerat-agent/service-standards.md",
            "ceerat-platform-builder-agent/.ceerat-agent/security-rbac-standard.md",
            "Prefer extending existing service boundaries when inventory shows ownership.",
            "Use contract-first service development.",
        ],
        required_output_from_codex=[
            "Concrete service ownership decision.",
            "Concrete proto messages/RPCs/full gRPC method names.",
            "Concrete handler/repository/model/migration changes.",
            "Concrete RBAC/public-method/ownership checks.",
            "Concrete logging/business event behavior.",
            "Concrete tests and verification commands.",
            "Integration impact only for existing apps/AI/infra callers.",
        ],
        warnings=[
            "Local mode is a fact/context packet, not an AI-generated final plan.",
            "Codex must perform the actual domain reasoning.",
            "If the request is ambiguous, Codex should ask or state assumptions before implementation.",
            "Use --mode ai when a cloud environment needs OpenAI to generate the final structured plan without Codex.",
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
    requirements_file: Optional[Path] = typer.Option(
        None,
        "--requirements-file",
        help="Optional JSON file with domain-specific must-have fields, relationships, and rules for local mode.",
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
            result = build_ai_plan(
                client=client,
                context=context,
                user_request=request,
            )
        else:
            result = _local_packet(request, Path(".").resolve(), requirements_file)
    except (ConfigError, ContextError, OpenAIClientError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if output == "json":
        if isinstance(result, PlanningPacket):
            _write_output(_packet_json(result), output_file)
        else:
            _write_output(_plan_json(result), output_file)
        return

    if isinstance(result, PlanningPacket):
        render_packet(result)
    else:
        render_plan(result)


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
    """Print the JSON schemas for local planning packets and AI implementation plans."""
    print(json.dumps({
        "local_planning_packet": PlanningPacket.model_json_schema(),
        "ai_implementation_plan": ImplementationPlan.model_json_schema(),
    }, indent=2, sort_keys=True))


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
