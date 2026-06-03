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
    expanded: List[str] = []
    previous = ""
    for ch in value:
        if ch.isupper() and previous and (previous.islower() or previous.isdigit()):
            expanded.append(" ")
        expanded.append(ch)
        previous = ch
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in "".join(expanded))
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
        "connect",
        "constraint",
        "create",
        "delete",
        "do",
        "does",
        "enable",
        "expose",
        "field",
        "fields",
        "fix",
        "for",
        "foreign",
        "get",
        "has",
        "have",
        "identify",
        "implement",
        "implementation",
        "index",
        "integrate",
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
        "page",
        "record",
        "records",
        "route",
        "service",
        "surface",
        "support",
        "the",
        "to",
        "ui",
        "unique",
        "update",
        "upgrade",
        "use",
        "wire",
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
            " ".join(
                " ".join([
                    method.get("name", ""),
                    method.get("request", ""),
                    method.get("response", ""),
                    method.get("full_method", ""),
                ])
                for method in service.get("methods", [])
            ),
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


def _suggested_contract_for_related(domain: str, related: RelatedContract) -> SuggestedContract:
    pascal = _pascal(domain)
    package = related.package or domain.replace("-", "_")
    service = related.service.split(".")[-1] if related.service else f"{pascal}Manager"
    full_service = related.service or f"{package}.{service}"
    rpcs = [
        SuggestedRPC(name=f"Create{pascal}", full_method=f"/{full_service}/Create{pascal}", request=f"Create{pascal}Request", response=f"{pascal}Response", purpose=f"Create a {domain} record."),
        SuggestedRPC(name=f"Get{pascal}", full_method=f"/{full_service}/Get{pascal}", request=f"Get{pascal}Request", response=f"{pascal}Response", purpose=f"Get one {domain} record."),
        SuggestedRPC(name=f"List{pascal}s", full_method=f"/{full_service}/List{pascal}s", request=f"List{pascal}sRequest", response=f"List{pascal}sResponse", purpose=f"List {domain} records."),
        SuggestedRPC(name=f"Update{pascal}", full_method=f"/{full_service}/Update{pascal}", request=f"Update{pascal}Request", response=f"{pascal}Response", purpose=f"Update a {domain} record."),
        SuggestedRPC(name=f"Delete{pascal}", full_method=f"/{full_service}/Delete{pascal}", request=f"Delete{pascal}Request", response=f"Delete{pascal}Response", purpose=f"Delete a {domain} record."),
    ]
    return SuggestedContract(
        package=package,
        service=service,
        proto_path=related.proto_path or f"packages/ceerat-contracts/proto/{package}/{package}.proto",
        rpcs=rpcs,
        messages=[
            pascal,
            f"Create{pascal}Request",
            f"Get{pascal}Request",
            f"List{pascal}sRequest",
            f"Update{pascal}Request",
            f"Delete{pascal}Request",
            f"{pascal}Response",
            f"List{pascal}sResponse",
            f"Delete{pascal}Response",
            "Error",
        ],
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


def _suggested_service_skeleton(domain: str, owner: RecommendedOwner, related: Optional[RelatedContract] = None) -> SuggestedServiceSkeleton:
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
                f"Expose {domain} RPCs through {related.service if related else _pascal(domain) + 'Manager'} registration.",
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


def _existing_rpc_match(request: str, related_contracts: List[RelatedContract]) -> Optional[RelatedContract]:
    request_words = set(_request_terms(request))
    if not request_words:
        return None
    for contract in related_contracts:
        for rpc in contract.rpcs:
            rpc_words = set(_words(rpc))
            if rpc_words and rpc_words <= request_words:
                return contract
            if len(rpc_words & request_words) >= 2:
                return contract
    return None


def _suppressed_contract(domain: str, related: Optional[RelatedContract]) -> SuggestedContract:
    if related:
        service = related.service.split(".")[-1] if related.service else "ExistingService"
        return SuggestedContract(
            package=related.package or domain.replace("-", "_"),
            service=service,
            proto_path=related.proto_path,
            rpcs=[],
            messages=[],
        )
    return SuggestedContract(
        package=domain.replace("-", "_"),
        service="ExistingOwner",
        proto_path="",
        rpcs=[],
        messages=[],
    )


def _suppressed_service_skeleton(owner: RecommendedOwner) -> SuggestedServiceSkeleton:
    return SuggestedServiceSkeleton(
        owner_project=owner.service_project,
        packages=[],
        files=[],
        startup_wiring=[
            "No new backend service skeleton suggested because the inventory already matched an existing backend capability.",
        ],
    )


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
    existing_rpc_owner = _existing_rpc_match(request, related_contracts)
    suppress_new_backend_skeleton = existing_rpc_owner is not None
    suggested_contract = (
        _suppressed_contract(domain, existing_rpc_owner)
        if suppress_new_backend_skeleton
        else _suggested_contract_for_related(domain, related_contracts[0]) if related_contracts else _suggested_contract(domain)
    )
    suggested_database_objects = [] if suppress_new_backend_skeleton else _suggested_database_objects(domain, requirements)
    suggested_service_skeleton = (
        _suppressed_service_skeleton(owner)
        if suppress_new_backend_skeleton
        else _suggested_service_skeleton(domain, owner, related_contracts[0] if related_contracts else None)
    )
    suggested_rbac_permissions = [] if suppress_new_backend_skeleton else _suggested_rbac(suggested_contract, domain)
    warnings = [
        "Local mode is a fact/context packet, not an AI-generated final plan.",
        "Codex must perform the actual domain reasoning.",
        "If the request is ambiguous, Codex should ask or state assumptions before implementation.",
        "Use --mode ai when a cloud environment needs OpenAI to generate the final structured plan without Codex.",
    ]
    if suppress_new_backend_skeleton:
        warnings.insert(
            0,
            "New backend skeleton suggestions were suppressed because an existing inventory RPC matched the request.",
        )

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
        suggested_database_objects=suggested_database_objects,
        suggested_service_skeleton=suggested_service_skeleton,
        suggested_rbac_permissions=suggested_rbac_permissions,
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
        warnings=warnings,
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


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _workspace_path(project_root: Path, relative_path: str) -> Path:
    return _workspace_root(project_root) / relative_path


def _safe_relative_files(root: Path, max_depth: int) -> List[str]:
    if not root.exists():
        return []
    files: List[str] = []
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if path.name in {".git", "__pycache__", ".venv", "node_modules", "bin"}:
            continue
        if any(part in {".git", "__pycache__", ".venv", "node_modules", "bin"} for part in path.relative_to(root).parts):
            continue
        depth = len(path.relative_to(root).parts)
        if depth > max_depth:
            continue
        suffix = "/" if path.is_dir() else ""
        files.append(str(path.relative_to(root)) + suffix)
    return files


def _service_pattern_payload() -> Dict[str, Any]:
    return {
        "kind": "service",
        "purpose": "Factual backend service implementation pattern for Codex before editing.",
        "standard_files": [
            "main.go wires DB, migrations, seed hooks, repositories, gRPC registration, reflection, admin HTTP hooks.",
            "<domain>/handler.go implements generated gRPC server methods and auth/ownership checks.",
            "<domain>/repository.go owns DB queries, transactions, filters, and persistence mapping.",
            "<domain>/handler_test.go follows existing gRPC/bufconn or handler test patterns.",
            "internal/models/models.go stores GORM entities migrated from main.go.",
        ],
        "wiring_steps": [
            "Add generated proto import in service main.",
            "Add model to AutoMigrate or migration path used by the service.",
            "Construct repository after DB connection.",
            "Register generated gRPC server on grpc.NewServer.",
            "Keep reflection enabled for local grpcurl/testing.",
        ],
        "reference_files": [
            "services-repo/services/ceerat-user-service/main.go",
            "services-repo/services/ceerat-user-service/orders/handler.go",
            "services-repo/services/ceerat-user-service/orders/repository.go",
            "services-repo/services/ceerat-user-service/orders/handler_test.go",
            "services-repo/services/ceerat-user-service/internal/models/models.go",
        ],
    }


def _grpc_security_pattern_payload() -> Dict[str, Any]:
    return {
        "kind": "grpc-security",
        "interceptor_order": "JWT -> RBAC -> logging -> handler for unary calls when JWT auth is enabled.",
        "must_update": [
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go: KnownGRPCMethods",
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go: DefaultRolePermissions",
            "contracts-repo/packages/ceerat-contracts/security/allowlist.go: DefaultPublicMethods only when a method is intentionally public",
        ],
        "handler_rules": [
            "Use authenticated user context for protected methods.",
            "Enforce ownership in handler/repository for customer/user-owned data.",
            "Do not rely on caller UI visibility for authorization.",
        ],
        "reference_files": [
            "services-repo/services/ceerat-user-service/main.go",
            "services-repo/services/ceerat-user-service/rbac.go",
            "contracts-repo/packages/ceerat-contracts/security/jwt_interceptor.go",
            "contracts-repo/packages/ceerat-contracts/security/rbac_interceptor.go",
            "contracts-repo/packages/ceerat-contracts/security/auth_context.go",
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            "contracts-repo/packages/ceerat-contracts/security/allowlist.go",
        ],
    }


def _repository_pattern_payload() -> Dict[str, Any]:
    return {
        "kind": "repository",
        "purpose": "Repository layer owns database access and should keep handler logic thin.",
        "rules": [
            "Keep SQL/GORM queries in repository packages, not app/UI code.",
            "Use transactions for multi-table writes.",
            "Return domain/proto-friendly values through handler mapping conventions.",
            "Add indexes for list filters and ownership checks.",
        ],
        "reference_files": [
            "services-repo/services/ceerat-user-service/orders/repository.go",
            "services-repo/services/ceerat-user-service/customers/repository.go",
            "services-repo/services/ceerat-user-service/services/repository.go",
            "services-repo/services/ceerat-user-service/user/repository.go",
        ],
    }


def _testing_pattern_payload() -> Dict[str, Any]:
    return {
        "kind": "testing",
        "commands": [
            "go test ./...",
            "go build ./...",
        ],
        "test_targets": [
            "handler tests for gRPC behavior and auth/ownership paths",
            "repository tests or focused DB tests when persistence logic is non-trivial",
            "security/RBAC tests when adding public or protected methods",
        ],
        "reference_files": [
            "services-repo/services/ceerat-user-service/orders/handler_test.go",
            "services-repo/services/ceerat-user-service/customers/handler_test.go",
            "contracts-repo/packages/ceerat-contracts/security/rbac_interceptor_test.go",
            "contracts-repo/packages/ceerat-contracts/security/jwt_interceptor_test.go",
            "services-repo/services/ceerat-user-service/docs/api-testing.md",
        ],
    }


def _patterns_payload(kind: str) -> Dict[str, Any]:
    patterns = {
        "service": _service_pattern_payload,
        "grpc-security": _grpc_security_pattern_payload,
        "security": _grpc_security_pattern_payload,
        "repository": _repository_pattern_payload,
        "testing": _testing_pattern_payload,
    }
    key = kind.lower().strip()
    if key not in patterns:
        raise ContextError("Unknown pattern. Use service, grpc-security, repository, or testing.")
    return patterns[key]()


def _read_doc_summary(path: Path, max_chars: int = 4000) -> Dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "summary": ""}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headings = [line for line in lines if line.startswith("#")][:20]
    return {
        "path": str(path),
        "exists": True,
        "headings": headings,
        "excerpt": text[:max_chars],
    }


def _cookbook_payload(project_root: Path, kind: str) -> Dict[str, Any]:
    if kind.lower().strip() != "service":
        raise ContextError("Unknown cookbook. Use service.")
    workspace = _workspace_root(project_root)
    paths = [
        workspace / "services-repo/services/ceerat-user-service/docs/new-service-cookbook.md",
        workspace / "services-repo/services/ceerat-user-service/docs/api.md",
        workspace / "services-repo/services/ceerat-user-service/docs/grpc-security.md",
        workspace / "services-repo/services/ceerat-user-service/docs/logging.md",
        workspace / "services-repo/services/ceerat-user-service/docs/api-testing.md",
    ]
    return {
        "kind": "service",
        "purpose": "Docs Codex should consult before creating or extending backend services.",
        "docs": [_read_doc_summary(path, max_chars=2500) for path in paths],
    }


def _requirements_payload(project_root: Path, domain: str, requirements_file: Optional[Path] = None) -> Dict[str, Any]:
    path = requirements_file or _default_requirements_path(project_root.resolve())
    requirements = _domain_requirements(domain, f"create {domain} service", path)
    return {
        "domain": domain,
        "requirements_file": str(path),
        "requirements": [item.model_dump() for item in requirements],
    }


def _verification_payload(service: str) -> Dict[str, Any]:
    service = service.strip()
    service_path = f"services-repo/services/{service}"
    return {
        "service": service,
        "workdir": service_path,
        "commands": [
            {"command": "go test ./...", "purpose": "Run service tests."},
            {"command": "go build ./...", "purpose": "Compile service packages."},
        ],
        "additional_checks": [
            "Run contract package tests if proto/security files changed.",
            "Run grpcurl against local stack when adding or changing gRPC methods.",
            "Check service logs for startup, migration, RBAC seed, and registration errors.",
        ],
        "related_workdirs": [
            "contracts-repo/packages/ceerat-contracts",
            "infra",
        ],
    }


def _service_full_methods_from_contracts(inventories: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    methods: Dict[str, List[Dict[str, Any]]] = {}
    for package in inventories["contracts"].get("proto_packages", []):
        service = package.get("service", {})
        full_service = service.get("full_service", "")
        if not full_service:
            continue
        methods[full_service] = []
        for rpc in service.get("rpcs", []):
            full_method = rpc.get("full_method") or f"/{full_service}/{rpc.get('name', '')}"
            methods[full_service].append({
                "name": rpc.get("name", ""),
                "full_method": full_method,
                "request": rpc.get("request", ""),
                "response": rpc.get("response", ""),
            })
    return methods


def _find_contract_service(inventories: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    target_words = set(_words(target))
    packages = inventories["contracts"].get("proto_packages", [])
    for package in packages:
        service = package.get("service", {})
        names = {
            package.get("package", ""),
            service.get("name", ""),
            service.get("full_service", ""),
        }
        if target in names:
            return package
    for package in packages:
        service = package.get("service", {})
        names = {
            package.get("package", ""),
            service.get("name", ""),
            service.get("full_service", ""),
        }
        haystack = set(_words(" ".join(names)))
        if target_words and target_words <= haystack:
            return package
    return None


def _find_service_inventory(inventories: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    target_words = set(_words(target))
    services = inventories["services"].get("grpc_services", [])
    for service in services:
        names = {
            service.get("name", ""),
            service.get("full_service", ""),
            service.get("owner_project", ""),
        }
        if target in names:
            return service
    for service in services:
        names = {
            service.get("name", ""),
            service.get("full_service", ""),
            service.get("owner_project", ""),
        }
        haystack = set(_words(" ".join(names)))
        if target_words and target_words <= haystack:
            return service
    return None


def _method_kind(name: str) -> str:
    if name.startswith(("Get", "List", "Search")):
        return "read"
    if name.startswith(("Create", "Update", "Delete", "Remove", "Assign")):
        return "write"
    return "unknown"


def _decision_payload(project_root: Path, request: str) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    domain = _domain_key(request)
    reqs = _domain_requirements(domain, request, _default_requirements_path(project_root.resolve()))
    contract_matches = _contract_matches(inventories, request)
    service_matches = _service_matches(inventories, request)
    app_matches = _app_matches(inventories, request)
    related = _related_contracts(inventories, request, reqs)

    if service_matches:
        recommendation = "extend_existing_service"
        owner = service_matches[0].name
        reason = service_matches[0].reason
    elif contract_matches:
        recommendation = "extend_existing_contract_owner"
        owner = contract_matches[0].name
        reason = contract_matches[0].reason
    elif related:
        recommendation = "extend_related_service"
        owner = related[0].service
        reason = related[0].reason
    else:
        recommendation = "requires_codex_decision"
        owner = "new-service-or-existing-module"
        reason = "No existing inventory owner matched strongly."

    service_inventory = _find_service_inventory(inventories, owner) if owner else None
    return {
        "request": request,
        "detected_domain": domain,
        "decision": {
            "recommendation": recommendation,
            "owner": owner,
            "reason": reason,
        },
        "inventory_matches": {
            "contracts": [item.model_dump() for item in contract_matches],
            "services": [item.model_dump() for item in service_matches],
            "apps_callers_only": [item.model_dump() for item in app_matches],
        },
        "related_contracts": [item.model_dump() for item in related],
        "recommended_files": [
            "contracts-repo/packages/ceerat-contracts/proto/service/service.proto",
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            "contracts-repo/packages/ceerat-contracts/domain/models.go",
            "contracts-repo/packages/ceerat-contracts/mapper/mapper.go",
            service_inventory.get("implementation_package", "services-repo/services/ceerat-user-service") if service_inventory else "services-repo/services",
            "services-repo/docs/grpc-service-inventory.json",
            "contracts-repo/docs/contract-inventory.json",
        ],
        "notes": [
            "Use this as evidence for ownership, not as final domain design.",
            "Apps inventory is caller compatibility context only for this service-focused builder.",
        ],
    }


def _contract_impact_payload(project_root: Path, target: str, add: Optional[str], remove: Optional[str]) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    contract = _find_contract_service(inventories, target)
    service = _find_service_inventory(inventories, target)
    full_service = contract.get("service", {}).get("full_service", target) if contract else target
    if add and remove:
        raise ContextError("Use either --add or --remove, not both.")
    if remove:
        return _contract_remove_impact_payload(inventories, target, remove, contract, service, full_service, project_root)
    capability = _pascal(add or "Capability")
    rpc_names = [
        f"Create{capability}",
        f"Get{capability}",
        f"List{capability}s",
        f"Update{capability}",
        f"Delete{capability}",
    ] if add else []
    return {
        "target": target,
        "capability": add,
        "contract_found": contract is not None,
        "service_found": service is not None,
        "full_service": full_service,
        "existing_rpcs": contract.get("service", {}).get("rpcs", []) if contract else [],
        "expected_new_contract_surface": {
            "rpc_names": rpc_names,
            "full_methods": [f"/{full_service}/{name}" for name in rpc_names],
            "messages": [
                capability,
                f"Create{capability}Request",
                f"Get{capability}Request",
                f"List{capability}sRequest",
                f"Update{capability}Request",
                f"Delete{capability}Request",
                f"{capability}Response",
                f"List{capability}sResponse",
            ] if add else [],
            "field_policy": "Do not infer business fields here. Use explicit user requirements and domain-requirements.json.",
        },
        "files_to_consider": [
            contract.get("proto_path", "contracts-repo/packages/ceerat-contracts/proto") if contract else "contracts-repo/packages/ceerat-contracts/proto",
            "contracts-repo/packages/ceerat-contracts/domain/models.go",
            "contracts-repo/packages/ceerat-contracts/mapper/mapper.go",
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            "contracts-repo/packages/ceerat-contracts/security/allowlist.go",
            "contracts-repo/docs/contract-inventory.json",
            service.get("implementation_package", "services-repo/services/ceerat-user-service") if service else "services-repo/services",
            "services-repo/docs/grpc-service-inventory.json",
        ],
        "commands": _proto_commands_payload(project_root, full_service)["commands"],
        "warnings": [
            "Regenerate proto outputs after editing .proto files.",
            "Update RBAC before running protected methods locally.",
            "Update both contract and service inventories after the implementation is settled.",
        ],
    }


def _contract_remove_impact_payload(
    inventories: Dict[str, Any],
    target: str,
    remove: str,
    contract: Optional[Dict[str, Any]],
    service: Optional[Dict[str, Any]],
    full_service: str,
    project_root: Path,
) -> Dict[str, Any]:
    capability = _pascal(remove)
    capability_words = set(_words(remove))
    capability_terms = {capability.lower(), f"{capability.lower()}s"}
    target_words = set(_words(target))
    package_name = contract.get("package", "") if contract else (target.split(".")[0] if "." in target else target)
    service_name = contract.get("service", {}).get("name", "") if contract else target.split(".")[-1]
    service_words = set(_words(" ".join([package_name, service_name, full_service])))
    whole_service_removal = bool(capability_words and capability_words <= service_words)

    existing_rpcs = contract.get("service", {}).get("rpcs", []) if contract else []
    methods_to_remove: List[Dict[str, Any]] = []
    for rpc in existing_rpcs:
        rpc_text = " ".join([
            rpc.get("name", ""),
            rpc.get("full_method", ""),
            rpc.get("request", ""),
            rpc.get("response", ""),
        ]).lower()
        if whole_service_removal or any(term in rpc_text for term in capability_terms):
            methods_to_remove.append(rpc)

    generated_files = contract.get("generated_files", []) if contract else []
    proto_path = contract.get("proto_path", "") if contract else ""
    if not proto_path and package_name:
        proto_path = f"contracts-repo/packages/ceerat-contracts/proto/{package_name}/{package_name}.proto"
    if not generated_files and package_name:
        generated_files = [
            f"contracts-repo/packages/ceerat-contracts/proto/{package_name}/{package_name}.pb.go",
            f"contracts-repo/packages/ceerat-contracts/proto/{package_name}/{package_name}_grpc.pb.go",
        ]

    domain_models = inventories["contracts"].get("domain_models", [])
    mapper_functions = inventories["contracts"].get("mapper_functions", [])
    matched_domain_models = [
        item for item in domain_models
        if any(term in item.get("name", "").lower() for term in capability_terms)
    ]
    matched_mapper_functions = [
        name for name in mapper_functions
        if any(term in name.lower() for term in capability_terms)
    ]
    known_methods = inventories["contracts"].get("security_contracts", {}).get("known_grpc_methods", [])
    security_methods_to_remove = [
        method for method in known_methods
        if method.startswith(f"/{full_service}/") and (whole_service_removal or capability.lower() in method.lower())
    ]

    implementation_package = service.get("implementation_package", "") if service else ""
    if not implementation_package and package_name:
        implementation_package = f"services-repo/services/ceerat-user-service/{package_name}s"

    return {
        "target": target,
        "operation": "remove",
        "capability": remove,
        "contract_found": contract is not None,
        "service_found": service is not None,
        "full_service": full_service,
        "whole_service_removal": whole_service_removal,
        "existing_rpcs": existing_rpcs,
        "expected_removed_contract_surface": {
            "proto_path": proto_path,
            "generated_files": generated_files,
            "rpc_methods": methods_to_remove,
            "security_methods": security_methods_to_remove,
            "domain_models": matched_domain_models,
            "mapper_functions": matched_mapper_functions,
            "field_policy": "Do not remove similarly named fields from unrelated domains without direct evidence.",
        },
        "files_to_consider": [
            proto_path or "contracts-repo/packages/ceerat-contracts/proto",
            *generated_files,
            "contracts-repo/packages/ceerat-contracts/Makefile",
            "contracts-repo/packages/ceerat-contracts/README.md",
            "contracts-repo/packages/ceerat-contracts/domain/models.go",
            "contracts-repo/packages/ceerat-contracts/mapper/mapper.go",
            "contracts-repo/packages/ceerat-contracts/mapper/mapper_test.go",
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            "contracts-repo/packages/ceerat-contracts/security/allowlist.go",
            "contracts-repo/docs/contract-inventory.json",
            implementation_package or "services-repo/services/ceerat-user-service",
            "services-repo/services/ceerat-user-service/main.go",
            "services-repo/services/ceerat-user-service/internal/models/models.go",
            "services-repo/docs/grpc-service-inventory.json",
            "services-repo/services/ceerat-user-service/docs",
            "apps-repo/docs",
            "apps-repo/docs/app-surface-inventory.json",
        ],
        "search_terms": sorted({
            remove,
            capability,
            capability.lower(),
            package_name,
            full_service,
            f"/{full_service}/",
            f"{capability}Entity",
            f"Register{capability}",
            f"{capability}Server",
        }),
        "removal_steps": [
            "Search all repos with the search_terms before deleting files.",
            "Remove the proto file and generated Go files only for the target capability/service.",
            "Remove contract domain models, mapper functions, mapper tests, and proto generation references.",
            "Remove KnownGRPCMethods, public allowlist entries if present, and default role permissions for removed methods.",
            "Remove service implementation package, model/entity mappings, AutoMigrate registration, repository construction, and gRPC server registration.",
            "Update contract and service inventories after the implemented surface is settled.",
            "Update focused docs and README references. Do not update .ceerat-agent standards until tests pass and a human validates the removal.",
            "Do not drop live database tables in this workflow. Document orphaned legacy tables for a later explicit migration decision.",
        ],
        "commands": [
            *_proto_commands_payload(project_root, full_service)["commands"],
            {"command": "go test ./...", "workdir": "services-repo/services/ceerat-user-service", "purpose": "Run service tests after service removal."},
            {"command": "go build ./...", "workdir": "services-repo/services/ceerat-user-service", "purpose": "Compile service packages after service removal."},
            {"command": "ceerat-builder check drift --output json", "workdir": "ceerat-platform-builder-agent", "purpose": "Confirm contract/service inventory and RBAC drift is clean."},
            {"command": "ceerat-builder check apps --output json", "workdir": "ceerat-platform-builder-agent", "purpose": "Confirm app inventory references still point to existing files."},
        ],
        "warnings": [
            "This is an impact packet, not a destructive command. The builder does not delete files.",
            "If contract_found=false, the capability may already be removed or the target name may not match inventory.",
            "Database table removal requires a separate explicit migration/drop approval.",
        ],
    }


def _rbac_suggestion_payload(project_root: Path, target: str, capability: Optional[str]) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    contract = _find_contract_service(inventories, target)
    full_service = contract.get("service", {}).get("full_service", target) if contract else target
    if capability:
        cap = _pascal(capability)
        methods = [
            {"name": f"Create{cap}", "full_method": f"/{full_service}/Create{cap}"},
            {"name": f"Get{cap}", "full_method": f"/{full_service}/Get{cap}"},
            {"name": f"List{cap}s", "full_method": f"/{full_service}/List{cap}s"},
            {"name": f"Update{cap}", "full_method": f"/{full_service}/Update{cap}"},
            {"name": f"Delete{cap}", "full_method": f"/{full_service}/Delete{cap}"},
        ]
    else:
        methods = _service_full_methods_from_contracts(inventories).get(full_service, [])

    suggested = []
    for method in methods:
        kind = _method_kind(method.get("name", ""))
        roles = ["admin", "agent"]
        if kind == "read":
            roles.append("customer")
        suggested.append({
            "method": method.get("full_method", ""),
            "method_kind": kind,
            "default_roles": roles,
            "public": False,
            "ownership_rule": "Handlers/repositories must enforce tenant/customer ownership for customer-visible records.",
        })
    return {
        "target": target,
        "capability": capability,
        "full_service": full_service,
        "suggested_permissions": suggested,
        "files_to_update": [
            "contracts-repo/packages/ceerat-contracts/security/grpc_methods.go",
            "contracts-repo/packages/ceerat-contracts/security/allowlist.go only if intentionally public",
            "services-repo/services/ceerat-user-service/docs/grpc-security.md if behavior changes",
            "contracts-repo/docs/contract-inventory.json",
            "services-repo/docs/grpc-service-inventory.json",
        ],
    }


def _security_inventory(inventories: Dict[str, Any]) -> Dict[str, Any]:
    return inventories["contracts"].get("security_contracts", {})


def _rbac_check_payload(project_root: Path) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    contract_methods = {
        method["full_method"]
        for methods in _service_full_methods_from_contracts(inventories).values()
        for method in methods
        if method.get("full_method")
    }
    service_methods = {
        method.get("full_method", "")
        for service in inventories["services"].get("grpc_services", [])
        for method in service.get("methods", [])
        if method.get("full_method")
    }
    security = _security_inventory(inventories)
    known = set(security.get("known_grpc_methods", []))
    public = set(security.get("default_public_methods", []))
    role_methods = {
        method
        for methods in security.get("default_role_permissions", {}).values()
        for method in methods
        if method != "*"
    }
    issues: List[Dict[str, Any]] = []
    for method in sorted(contract_methods - known - public):
        issues.append({"severity": "high", "type": "missing_known_grpc_method", "method": method})
    for method in sorted(role_methods - known - public):
        issues.append({"severity": "high", "type": "role_permission_not_known_or_public", "method": method})
    for method in sorted(service_methods - contract_methods):
        issues.append({"severity": "medium", "type": "service_inventory_method_missing_from_contract_inventory", "method": method})
    for method in sorted(contract_methods - service_methods):
        issues.append({"severity": "medium", "type": "contract_method_missing_from_service_inventory", "method": method})
    return {
        "ok": not issues,
        "contract_methods": len(contract_methods),
        "service_inventory_methods": len(service_methods),
        "known_grpc_methods": len(known),
        "public_methods": len(public),
        "role_permission_methods": len(role_methods),
        "issues": issues,
    }


def _model_evidence_payload(project_root: Path, model_name: str) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    needle = model_name.lower()
    proto_messages = []
    rpcs = []
    for package in inventories["contracts"].get("proto_packages", []):
        for message in package.get("messages", []):
            if needle in message.get("name", "").lower():
                proto_messages.append({
                    "package": package.get("package", ""),
                    "proto_path": package.get("proto_path", ""),
                    "message": message,
                })
        for rpc in package.get("service", {}).get("rpcs", []):
            haystack = " ".join([rpc.get("name", ""), rpc.get("request", ""), rpc.get("response", "")]).lower()
            if needle in haystack:
                rpcs.append({
                    "service": package.get("service", {}).get("full_service", ""),
                    "proto_path": package.get("proto_path", ""),
                    "rpc": rpc,
                })
    domain_models = [
        model for model in inventories["contracts"].get("domain_models", [])
        if needle in model.get("name", "").lower()
    ]
    mappers = []
    for mapper in inventories["contracts"].get("mapper_functions", []):
        if isinstance(mapper, str):
            if needle in mapper.lower():
                mappers.append(mapper)
        elif needle in " ".join(mapper.get("functions", [])).lower():
            mappers.append(mapper)
    service_methods = [
        {
            "service": service.get("full_service", ""),
            "implementation_package": service.get("implementation_package", ""),
            "method": method,
        }
        for service in inventories["services"].get("grpc_services", [])
        for method in service.get("methods", [])
        if needle in " ".join([method.get("name", ""), method.get("request", ""), method.get("response", "")]).lower()
    ]
    return {
        "model": model_name,
        "found": bool(proto_messages or domain_models or mappers or service_methods),
        "proto_messages": proto_messages,
        "domain_models": domain_models,
        "mapper_functions": mappers,
        "service_methods": service_methods,
        "file_hints": [
            "contracts-repo/packages/ceerat-contracts/domain/models.go",
            "contracts-repo/packages/ceerat-contracts/mapper/mapper.go",
            "contracts-repo/packages/ceerat-contracts/proto",
            "services-repo/services/ceerat-user-service/internal/models/models.go",
        ],
    }


def _proto_commands_payload(project_root: Path, target: str) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    contract = _find_contract_service(inventories, target)
    proto_path = contract.get("proto_path", "contracts-repo/packages/ceerat-contracts/proto") if contract else "contracts-repo/packages/ceerat-contracts/proto"
    return {
        "target": target,
        "workdir": "contracts-repo/packages/ceerat-contracts",
        "proto_path": proto_path,
        "commands": [
            {"command": "make proto", "purpose": "Regenerate Go protobuf and gRPC files after .proto edits."},
            {"command": "go test ./...", "purpose": "Run contract, mapper, and security tests."},
            {"command": "go build ./...", "purpose": "Compile generated contract package."},
        ],
        "expected_generated_files": [
            "contracts-repo/packages/ceerat-contracts/proto/**/*.pb.go",
            "contracts-repo/packages/ceerat-contracts/proto/**/*_grpc.pb.go",
        ],
    }


def _inventory_patch_hints_payload(project_root: Path, target: str) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    contract = _find_contract_service(inventories, target)
    service = _find_service_inventory(inventories, target)
    return {
        "target": target,
        "contract_inventory": {
            "path": "contracts-repo/docs/contract-inventory.json",
            "patch_sections": [
                "proto_packages[].service.rpcs",
                "proto_packages[].messages",
                "domain_models",
                "mapper_functions",
                "security_contracts.known_grpc_methods",
                "security_contracts.default_role_permissions",
            ],
            "current_contract": contract,
        },
        "service_inventory": {
            "path": "services-repo/docs/grpc-service-inventory.json",
            "patch_sections": [
                "grpc_services[].methods",
                "grpc_services[].implementation_package",
                "grpc_services[].default_role_permissions_summary",
                "backend_services[].docs",
            ],
            "current_service": service,
        },
        "apps_inventory": {
            "path": "apps-repo/docs/app-surface-inventory.json",
            "patch_when": "Only update when app handlers, routes, templates, static files, or AI tools changed.",
        },
    }


def _verification_contract_and_service_payload(target: str) -> Dict[str, Any]:
    return {
        "scope": "contract-and-service",
        "target": target,
        "commands": [
            {
                "workdir": "contracts-repo/packages/ceerat-contracts",
                "command": "make proto",
                "purpose": "Regenerate generated protobuf files.",
            },
            {
                "workdir": "contracts-repo/packages/ceerat-contracts",
                "command": "go test ./...",
                "purpose": "Run contract, mapper, and security tests.",
            },
            {
                "workdir": "contracts-repo/packages/ceerat-contracts",
                "command": "go build ./...",
                "purpose": "Compile contract package.",
            },
            {
                "workdir": "services-repo/services/ceerat-user-service",
                "command": "go test ./...",
                "purpose": "Run service implementation tests.",
            },
            {
                "workdir": "services-repo/services/ceerat-user-service",
                "command": "go build ./...",
                "purpose": "Compile service packages.",
            },
            {
                "workdir": "ceerat-platform-builder-agent",
                "command": "ceerat-builder check drift --output json",
                "purpose": "Check inventory/security drift after edits.",
            },
        ],
        "manual_checks": [
            "Start infra stack and call changed methods with grpcurl when runtime behavior changed.",
            "Check logs for startup, migration, RBAC seed, and registration errors.",
            "Confirm inventories describe the final implemented surface.",
        ],
        "post_human_validation_checklist": _post_validation_checklist(),
    }


def _post_validation_checklist() -> List[str]:
    return [
        "Only after tests pass and a human validates behavior, update builder-agent standards if the platform pattern changed.",
        "Update .ceerat-agent docs for durable builder knowledge: architecture, module-generation-standard, service-standards, security-rbac-standard, ai-tool-standard when relevant.",
        "Update service docs for user-facing truth: api.md, api-testing.md, grpc-security.md, logging.md, architecture.md, and cookbook docs when relevant.",
        "Update inventories that describe the final surface: contract-inventory.json, grpc-service-inventory.json, app-surface-inventory.json when relevant.",
        "Run ceerat-builder check drift --output json and ceerat-builder check apps --output json after doc/inventory updates.",
    ]


def _drift_payload(project_root: Path) -> Dict[str, Any]:
    rbac = _rbac_check_payload(project_root)
    issues = list(rbac["issues"])
    inventories = _load_inventories(project_root)
    contract_services = {
        package.get("service", {}).get("full_service", "")
        for package in inventories["contracts"].get("proto_packages", [])
        if package.get("service", {}).get("full_service")
    }
    service_services = {
        service.get("full_service", "")
        for service in inventories["services"].get("grpc_services", [])
        if service.get("full_service")
    }
    for service in sorted(contract_services - service_services):
        issues.append({"severity": "medium", "type": "contract_service_missing_from_service_inventory", "service": service})
    for service in sorted(service_services - contract_services):
        issues.append({"severity": "medium", "type": "service_inventory_missing_from_contract_inventory", "service": service})
    return {
        "ok": not issues,
        "issues": issues,
        "checked": [
            "contract proto RPCs vs KnownGRPCMethods",
            "DefaultRolePermissions vs known/public methods",
            "contracts inventory methods vs services inventory methods",
            "contracts inventory services vs services inventory services",
        ],
    }


def _docs_payload(project_root: Path, scope: str) -> Dict[str, Any]:
    scope = scope.lower().strip()
    workspace = _workspace_root(project_root)
    docs = {
        "builder": [
            {
                "path": "ceerat-platform-builder-agent/.ceerat-agent/architecture.md",
                "purpose": "Platform/service-builder architecture context.",
            },
            {
                "path": "ceerat-platform-builder-agent/.ceerat-agent/module-generation-standard.md",
                "purpose": "Service module planning and ownership standards.",
            },
            {
                "path": "ceerat-platform-builder-agent/.ceerat-agent/service-standards.md",
                "purpose": "Detailed backend service implementation standards.",
            },
            {
                "path": "ceerat-platform-builder-agent/.ceerat-agent/security-rbac-standard.md",
                "purpose": "JWT/RBAC/ownership standards.",
            },
            {
                "path": "ceerat-platform-builder-agent/.ceerat-agent/ai-tool-standard.md",
                "purpose": "AI tool and platform client standards.",
            },
            {
                "path": "ceerat-platform-builder-agent/.ceerat-agent/domain-requirements.json",
                "purpose": "Explicit domain requirements that should not be inferred by the builder.",
            },
        ],
        "service": [
            {
                "path": "services-repo/services/ceerat-user-service/docs/api.md",
                "purpose": "Focused gRPC/admin HTTP API reference.",
            },
            {
                "path": "services-repo/services/ceerat-user-service/docs/api-testing.md",
                "purpose": "grpcurl/curl testing guide.",
            },
            {
                "path": "services-repo/services/ceerat-user-service/docs/grpc-security.md",
                "purpose": "gRPC auth, RBAC, ownership, and public method behavior.",
            },
            {
                "path": "services-repo/services/ceerat-user-service/docs/logging.md",
                "purpose": "Structured logging and business event guidance.",
            },
            {
                "path": "services-repo/services/ceerat-user-service/docs/architecture.md",
                "purpose": "50,000 foot platform/service architecture.",
            },
            {
                "path": "services-repo/services/ceerat-user-service/docs/ceerat-user-service-architecture.md",
                "purpose": "Detailed user-service architecture.",
            },
            {
                "path": "services-repo/services/ceerat-user-service/docs/ceerat-user-service-architecture.html",
                "purpose": "HTML visual architecture companion.",
            },
            {
                "path": "services-repo/services/ceerat-user-service/docs/new-service-cookbook.md",
                "purpose": "Recipe for creating or extending services.",
            },
        ],
        "inventory": [
            {
                "path": "contracts-repo/docs/contract-inventory.json",
                "purpose": "Contract/proto/security inventory.",
            },
            {
                "path": "services-repo/docs/grpc-service-inventory.json",
                "purpose": "Backend gRPC service inventory.",
            },
            {
                "path": "apps-repo/docs/app-surface-inventory.json",
                "purpose": "App handlers/templates/static/chat/AI tool inventory.",
            },
        ],
        "apps": [
            {
                "path": "apps-repo/docs/app-surface-inventory.json",
                "purpose": "App surface source of truth.",
            },
            {
                "path": "apps-repo/apps/ceerat-admin-ui/docs/admin-ui-architecture.html",
                "purpose": "Admin UI architecture.",
            },
            {
                "path": "apps-repo/apps/ceerat-customer-ui/docs/customer-ui-architecture.html",
                "purpose": "Customer UI architecture.",
            },
            {
                "path": "apps-repo/apps/ceerat-web-ui/docs/web-ui-architecture.html",
                "purpose": "Web UI architecture when present.",
            },
            {
                "path": "apps-repo/ai/docs/ai-chat-architecture.md",
                "purpose": "AI chat architecture.",
            },
            {
                "path": "apps-repo/ai/docs/agent-tools.md",
                "purpose": "AI tool inventory and behavior.",
            },
        ],
    }
    aliases = {
        "all": ["builder", "service", "inventory", "apps"],
        "builder-agent": ["builder"],
        "services": ["service"],
        "service-docs": ["service"],
        "inventories": ["inventory"],
        "app": ["apps"],
    }
    selected = aliases.get(scope, [scope])
    unknown = [item for item in selected if item not in docs]
    if unknown:
        raise ContextError("Unknown docs scope. Use all, builder, service, inventory, or apps.")
    resolved: List[Dict[str, Any]] = []
    for key in selected:
        for doc in docs[key]:
            abs_path = workspace / doc["path"]
            resolved.append({
                **doc,
                "scope": key,
                "exists": abs_path.exists(),
                "absolute_path": str(abs_path),
            })
    return {
        "scope": scope,
        "purpose": "Relevant Ceerat documentation locations for Codex/builder workflows.",
        "post_human_validation_checklist": _post_validation_checklist(),
        "docs": resolved,
    }


def _app_items(inventories: Dict[str, Any]) -> List[Dict[str, Any]]:
    return inventories["apps"].get("browser_apps", []) + inventories["apps"].get("ai_apps", [])


def _find_app(inventories: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    target_words = set(_words(target))
    for app_item in _app_items(inventories):
        names = {app_item.get("name", ""), app_item.get("path", ""), app_item.get("type", "")}
        if target in names:
            return app_item
    for app_item in _app_items(inventories):
        names = {app_item.get("name", ""), app_item.get("path", ""), app_item.get("type", "")}
        haystack = set(_words(" ".join(names)))
        if target_words and target_words <= haystack:
            return app_item
    return None


def _app_route_source(inventories: Dict[str, Any], app_name: str) -> str:
    source = inventories["apps"].get("source_of_truth", {})
    keys = {
        "ceerat-admin-ui": "admin_ui_routes",
        "ceerat-web-ui": "web_ui_routes",
        "ceerat-customer-ui": "customer_ui_routes",
        "ceerat-agent-service": "agent_service_routes",
    }
    return source.get(keys.get(app_name, ""), "")


def _app_context_payload(project_root: Path, target: Optional[str]) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    apps = _app_items(inventories)
    selected = [_find_app(inventories, target)] if target else apps
    selected = [app_item for app_item in selected if app_item]
    return {
        "scope": "apps",
        "target": target or "all",
        "purpose": "Lightweight app discovery context. Use this for route/template/static/caller awareness, not final UI design.",
        "inventory": "apps-repo/docs/app-surface-inventory.json",
        "source_of_truth": inventories["apps"].get("source_of_truth", {}),
        "apps": [
            {
                "name": app_item.get("name", ""),
                "path": app_item.get("path", ""),
                "type": app_item.get("type", ""),
                "default_port": app_item.get("default_port", ""),
                "session_cookie": app_item.get("session_cookie", ""),
                "dependencies": app_item.get("dependencies", []),
                "config": app_item.get("config", {}),
                "handler_count": len(app_item.get("handlers", [])),
                "template_count": len(app_item.get("templates", [])),
                "static_file_count": len(app_item.get("static_files", [])),
                "chatgpt_client_file_count": len(app_item.get("chatgpt_client_files", [])),
                "tools": app_item.get("tools", []),
                "code_inventory": app_item.get("code_inventory", {}),
            }
            for app_item in selected
        ],
        "active_chat_surfaces": inventories["apps"].get("active_chat_surfaces", []),
        "rules": inventories["apps"].get("inventory_rules", []),
        "checklist": inventories["apps"].get("builder_checklist_before_new_app_surface", []),
    }


def _app_surface_payload(project_root: Path, target: str) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    app_item = _find_app(inventories, target)
    if not app_item:
        raise ContextError(f"Unknown app: {target}")
    return {
        "app": app_item.get("name", target),
        "path": app_item.get("path", ""),
        "type": app_item.get("type", ""),
        "handlers": app_item.get("handlers", []),
        "templates": app_item.get("templates", []),
        "static_files": app_item.get("static_files", []),
        "chatgpt_client_files": app_item.get("chatgpt_client_files", []),
        "tools": app_item.get("tools", []),
        "dependencies": app_item.get("dependencies", []),
        "code_inventory": app_item.get("code_inventory", {}),
    }


def _app_match_payload(project_root: Path, request: str) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    terms = set(_request_terms(request))
    matches: List[Dict[str, Any]] = []
    for app_item in _app_items(inventories):
        fields = [
            app_item.get("name", ""),
            app_item.get("type", ""),
            " ".join(app_item.get("dependencies", [])),
            " ".join(app_item.get("tools", [])),
            " ".join(app_item.get("templates", [])),
            " ".join(app_item.get("static_files", [])),
            " ".join(app_item.get("chatgpt_client_files", [])),
        ]
        for handler in app_item.get("handlers", []):
            fields.append(" ".join(str(value) for value in handler.values()))
        shared = sorted(terms & set(_words(" ".join(fields))))
        if shared:
            matches.append({
                "app": app_item.get("name", ""),
                "path": app_item.get("path", ""),
                "type": app_item.get("type", ""),
                "matched_terms": shared,
                "matching_handlers": [
                    handler for handler in app_item.get("handlers", [])
                    if terms & set(_words(" ".join(str(value) for value in handler.values())))
                ],
                "matching_templates": [
                    path for path in app_item.get("templates", [])
                    if terms & set(_words(path))
                ],
                "matching_static_files": [
                    path for path in app_item.get("static_files", []) + app_item.get("chatgpt_client_files", [])
                    if terms & set(_words(path))
                ],
                "matching_tools": [
                    tool for tool in app_item.get("tools", [])
                    if terms & set(_words(tool))
                ],
            })
    chat_matches = []
    for surface in inventories["apps"].get("active_chat_surfaces", []):
        shared = sorted(terms & set(_words(" ".join(str(value) for value in surface.values()))))
        if shared:
            chat_matches.append({"matched_terms": shared, **surface})
    return {
        "request": request,
        "matches": matches,
        "active_chat_surface_matches": chat_matches,
        "guidance": [
            "Extend an existing route/surface when a close match exists.",
            "Business operations should continue through backend service APIs.",
            "Update apps-repo/docs/app-surface-inventory.json when adding or removing routes, templates, static files, chat assets, AI endpoints, or tools.",
        ],
    }


def _app_impact_payload(project_root: Path, target: str, route: Optional[str], surface: Optional[str]) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    app_item = _find_app(inventories, target)
    if not app_item:
        raise ContextError(f"Unknown app: {target}")
    app_path = app_item.get("path", "")
    commands = [
        {"workdir": f"apps-repo/{app_path}", "command": "go test ./...", "purpose": "Run app tests if present."},
        {"workdir": f"apps-repo/{app_path}", "command": "go build ./...", "purpose": "Compile app packages."},
    ]
    return {
        "app": app_item.get("name", target),
        "path": app_path,
        "requested_route": route,
        "requested_surface": surface,
        "existing_handlers": app_item.get("handlers", []),
        "files_to_inspect": [
            _app_route_source(inventories, app_item.get("name", "")),
            *app_item.get("templates", []),
            *app_item.get("static_files", []),
            *app_item.get("chatgpt_client_files", []),
        ],
        "inventory_updates": [
            "apps-repo/docs/app-surface-inventory.json browser_apps[].handlers or ai_apps[].handlers",
            "apps-repo/docs/app-surface-inventory.json templates/static_files/chatgpt_client_files/tools when changed",
            "apps-repo/docs/app-surface-inventory.json active_chat_surfaces when chat wiring changes",
        ],
        "dependency_notes": app_item.get("dependencies", []),
        "commands": commands,
        "boundaries": [
            "This builder only discovers app surfaces for now.",
            "Do not use app discovery as a final UI design standard.",
            "Do not add direct database access from browser apps.",
        ],
    }


def _app_check_payload(project_root: Path) -> Dict[str, Any]:
    inventories = _load_inventories(project_root)
    workspace = _workspace_root(project_root)
    issues: List[Dict[str, Any]] = []
    for app_item in _app_items(inventories):
        routes: Dict[str, int] = {}
        for handler in app_item.get("handlers", []):
            route = handler.get("route", "")
            if route:
                routes[route] = routes.get(route, 0) + 1
        for route, count in sorted(routes.items()):
            if count > 1:
                issues.append({
                    "severity": "medium",
                    "type": "duplicate_route_in_app_inventory",
                    "app": app_item.get("name", ""),
                    "route": route,
                    "count": count,
                })
        for file_path in app_item.get("templates", []) + app_item.get("static_files", []) + app_item.get("chatgpt_client_files", []):
            candidate = workspace / "apps-repo" / file_path
            if not candidate.exists():
                issues.append({
                    "severity": "low",
                    "type": "inventory_file_missing_on_disk",
                    "app": app_item.get("name", ""),
                    "path": file_path,
                })
    return {
        "ok": not issues,
        "issues": issues,
        "checked": [
            "duplicate routes inside each app inventory entry",
            "template/static/chat asset inventory paths exist on disk",
        ],
    }


def _codex_context_payload(project_root: Path) -> Dict[str, Any]:
    return {
        "purpose": "Fast starting context for Codex service work.",
        "first_commands": [
            "ceerat-builder inventory services --output json",
            "ceerat-builder inventory contracts --output json",
            "ceerat-builder decide-owner \"<request>\" --output json",
            "ceerat-builder patterns service --output json",
            "ceerat-builder patterns grpc-security --output json",
            "ceerat-builder evidence request \"<request>\" --output json",
            "ceerat-builder rbac check --output json",
            "ceerat-builder check drift --output json",
            "ceerat-builder plan --output json \"<request>\"",
            "ceerat-builder docs service --output json",
        ],
        "app_discovery_commands": [
            "ceerat-builder app-context --output json",
            "ceerat-builder app-surface ceerat-web-ui --output json",
            "ceerat-builder app-match \"<request>\" --output json",
            "ceerat-builder app-impact ceerat-web-ui --route \"GET /example\" --output json",
            "ceerat-builder check apps --output json",
        ],
        "standards": [
            ".ceerat-agent/architecture.md",
            ".ceerat-agent/module-generation-standard.md",
            ".ceerat-agent/service-standards.md",
            ".ceerat-agent/security-rbac-standard.md",
        ],
        "inventories": {
            "services": str(_workspace_path(project_root, "services-repo/docs/grpc-service-inventory.json")),
            "contracts": str(_workspace_path(project_root, "contracts-repo/docs/contract-inventory.json")),
            "apps": str(_workspace_path(project_root, "apps-repo/docs/app-surface-inventory.json")),
        },
        "rules": [
            "Use builder output as factual context, not final design.",
            "Use requirements files for business/domain must-haves.",
            "Keep apps/AI inventory as caller compatibility only for service builder work.",
            "Update builder-agent standards only after tests pass and a human validates behavior.",
        ],
        "post_human_validation_checklist": _post_validation_checklist(),
    }


@app.command("inventory")
def inventory(
    kind: Optional[str] = typer.Argument(
        None,
        help="Optional inventory kind: all, services, contracts, or apps.",
    ),
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
    kind = (kind or "all").lower().strip()
    if output not in {"summary", "json"}:
        error_console.print("[bold red]Error:[/bold red] --output must be summary or json")
        raise typer.Exit(code=2)
    if kind not in {"all", "services", "contracts", "apps"}:
        error_console.print("[bold red]Error:[/bold red] kind must be all, services, contracts, or apps")
        raise typer.Exit(code=2)
    try:
        inventories = _load_inventories(project_root)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if output == "json":
        payload = inventories if kind == "all" else {kind: inventories[kind]}
        _print_json(payload)
        return

    if kind != "all":
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Inventory", style="bold")
        table.add_column("Summary")
        payload = inventories[kind]
        if kind == "services":
            rows = [f"{item.get('full_service', item.get('name', ''))}: {item.get('implementation_package', item.get('path', ''))}" for item in payload.get("grpc_services", [])]
        elif kind == "contracts":
            rows = [f"{item.get('package', '')}: {item.get('proto_path', '')}" for item in payload.get("proto_packages", [])]
        else:
            rows = [f"{item.get('name', '')}: {item.get('path', '')}" for item in payload.get("browser_apps", []) + payload.get("ai_apps", [])]
        table.add_row(kind, "\n".join(rows) if rows else "None")
        console.print(table)
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


@app.command("decide-owner")
def decide_owner(
    request: str = typer.Argument(..., help='Service request, such as "create product service".'),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return inventory-backed service ownership decision evidence."""
    output = output.lower().strip()
    try:
        payload = _decision_payload(project_root, request)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Decision", payload["decision"]["recommendation"])
    table.add_row("Owner", payload["decision"]["owner"])
    table.add_row("Reason", payload["decision"]["reason"])
    console.print(table)


@app.command("impact")
def impact(
    kind: str = typer.Argument(..., help="Impact kind. Currently: contract."),
    target: str = typer.Argument(..., help="Target service, such as service.ServiceManager."),
    add: Optional[str] = typer.Option(None, "--add", help="Optional capability/model being added."),
    remove: Optional[str] = typer.Option(None, "--remove", help="Optional capability/model/service being removed."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return files and surfaces likely impacted by a service contract add/remove."""
    output = output.lower().strip()
    if kind.lower().strip() != "contract":
        error_console.print("[bold red]Error:[/bold red] impact kind must be contract")
        raise typer.Exit(code=2)
    try:
        payload = _contract_impact_payload(project_root, target, add, remove)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Area")
    table.add_column("Value")
    table.add_row("Operation", payload.get("operation", "add"))
    table.add_row("Full service", payload["full_service"])
    table.add_row("Files", "\n".join(payload["files_to_consider"]))
    console.print(table)


@app.command("rbac")
def rbac(
    action: str = typer.Argument(..., help="RBAC action: suggest or check."),
    target: Optional[str] = typer.Argument(None, help="Target gRPC service for suggest."),
    capability: Optional[str] = typer.Option(None, "--capability", help="Optional capability/model name for suggest."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Suggest or check gRPC RBAC inventory/security data."""
    output = output.lower().strip()
    action = action.lower().strip()
    try:
        if action == "suggest":
            if not target:
                error_console.print("[bold red]Error:[/bold red] rbac suggest requires a target")
                raise typer.Exit(code=2)
            payload = _rbac_suggestion_payload(project_root, target, capability)
        elif action == "check":
            payload = _rbac_check_payload(project_root)
        else:
            error_console.print("[bold red]Error:[/bold red] rbac action must be suggest or check")
            raise typer.Exit(code=2)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Item")
    table.add_column("Value")
    if action == "check":
        table.add_row("OK", str(payload["ok"]))
        table.add_row("Issues", "\n".join(str(issue) for issue in payload["issues"]) or "None")
    else:
        for item in payload["suggested_permissions"]:
            table.add_row(item["method"], ", ".join(item["default_roles"]))
    console.print(table)


@app.command("proto-commands")
def proto_commands(
    target: str = typer.Argument("service", help="Target proto package/service."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return contract/proto regeneration commands for Codex."""
    output = output.lower().strip()
    try:
        payload = _proto_commands_payload(project_root, target)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Command")
    table.add_column("Purpose")
    for item in payload["commands"]:
        table.add_row(item["command"], item["purpose"])
    console.print(table)


@app.command("inventory-patch-hints")
def inventory_patch_hints(
    target: str = typer.Argument(..., help="Target service or contract, such as service.ServiceManager."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return inventory sections that usually need updates after service changes."""
    output = output.lower().strip()
    try:
        payload = _inventory_patch_hints_payload(project_root, target)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Inventory")
    table.add_column("Sections")
    table.add_row(payload["contract_inventory"]["path"], "\n".join(payload["contract_inventory"]["patch_sections"]))
    table.add_row(payload["service_inventory"]["path"], "\n".join(payload["service_inventory"]["patch_sections"]))
    table.add_row(payload["apps_inventory"]["path"], payload["apps_inventory"]["patch_when"])
    console.print(table)


@app.command("docs")
def docs(
    scope: str = typer.Argument("all", help="Docs scope: all, builder, service, inventory, or apps."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return relevant docs for Codex/builder workflows and post-validation updates."""
    output = output.lower().strip()
    try:
        payload = _docs_payload(project_root, scope)
    except ContextError as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Scope")
    table.add_column("Path")
    table.add_column("Purpose")
    table.add_column("Exists")
    for item in payload["docs"]:
        table.add_row(item["scope"], item["path"], item["purpose"], str(item["exists"]))
    console.print(table)


@app.command("check")
def check(
    kind: str = typer.Argument(..., help="Check kind: drift or apps."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Run non-mutating consistency checks over inventories and security data."""
    output = output.lower().strip()
    kind = kind.lower().strip()
    if kind not in {"drift", "apps"}:
        error_console.print("[bold red]Error:[/bold red] check kind must be drift or apps")
        raise typer.Exit(code=2)
    try:
        payload = _app_check_payload(project_root) if kind == "apps" else _drift_payload(project_root)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Severity")
    table.add_column("Issue")
    for issue in payload["issues"]:
        table.add_row(issue.get("severity", ""), json.dumps(issue, sort_keys=True))
    if not payload["issues"]:
        table.add_row("ok", "No drift issues found.")
    console.print(table)


@app.command("app-context")
def app_context(
    target: Optional[str] = typer.Argument(None, help="Optional app name, such as ceerat-web-ui."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return lightweight discovery context for browser and AI apps."""
    output = output.lower().strip()
    try:
        payload = _app_context_payload(project_root, target)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("App")
    table.add_column("Summary")
    for app_item in payload["apps"]:
        table.add_row(app_item["name"], f"{app_item['handler_count']} handlers, {app_item['template_count']} templates, {app_item['static_file_count']} static files")
    console.print(table)


@app.command("app-surface")
def app_surface(
    target: str = typer.Argument(..., help="App name, such as ceerat-web-ui."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return handlers, templates, static files, tools, and dependencies for one app."""
    output = output.lower().strip()
    try:
        payload = _app_surface_payload(project_root, target)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Route")
    table.add_column("Handler")
    for handler in payload["handlers"]:
        table.add_row(handler.get("route", ""), handler.get("handler", ""))
    console.print(table)


@app.command("app-match")
def app_match(
    request: str = typer.Argument(..., help='App request, such as "add product page".'),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Find existing app routes, files, chat surfaces, and tools related to a request."""
    output = output.lower().strip()
    try:
        payload = _app_match_payload(project_root, request)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("App")
    table.add_column("Matched")
    for match in payload["matches"]:
        table.add_row(match["app"], ", ".join(match["matched_terms"]))
    console.print(table)


@app.command("app-impact")
def app_impact(
    target: str = typer.Argument(..., help="App name, such as ceerat-web-ui."),
    route: Optional[str] = typer.Option(None, "--route", help='Optional route being added or changed, such as "GET /products".'),
    surface: Optional[str] = typer.Option(None, "--surface", help="Optional surface name, such as products page or chat panel."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return likely app files, inventory sections, and verification commands for an app change."""
    output = output.lower().strip()
    try:
        payload = _app_impact_payload(project_root, target, route, surface)
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Area")
    table.add_column("Value")
    table.add_row("Files", "\n".join(path for path in payload["files_to_inspect"] if path))
    table.add_row("Commands", "\n".join(f"{item['workdir']}: {item['command']}" for item in payload["commands"]))
    console.print(table)


@app.command("structure")
def structure(
    target: str = typer.Argument(
        ...,
        help="Target tree: services-repo, contracts-repo, apps-repo, ceerat-user-service, or a relative path.",
    ),
    output: str = typer.Option(
        "json",
        "--output",
        "-o",
        help="Output format: json or table.",
    ),
    max_depth: int = typer.Option(
        3,
        "--max-depth",
        help="Maximum relative path depth to include.",
    ),
    project_root: Path = typer.Option(
        Path("."),
        "--project-root",
        help="Builder repo root, or workspace root containing sibling repos.",
    ),
) -> None:
    """Print a compact repo/file structure for Codex discovery."""
    output = output.lower().strip()
    aliases = {
        "services-repo": "services-repo",
        "contracts-repo": "contracts-repo",
        "apps-repo": "apps-repo",
        "ceerat-user-service": "services-repo/services/ceerat-user-service",
        "contracts": "contracts-repo/packages/ceerat-contracts",
    }
    relative = aliases.get(target, target)
    root = _workspace_path(project_root, relative)
    payload = {
        "target": target,
        "path": str(root),
        "max_depth": max_depth,
        "entries": _safe_relative_files(root, max_depth),
    }
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Path")
    for entry in payload["entries"]:
        table.add_row(entry)
    console.print(table)


@app.command("patterns")
def patterns(
    kind: str = typer.Argument(..., help="Pattern kind: service, grpc-security, repository, or testing."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
) -> None:
    """Return reusable service implementation patterns."""
    output = output.lower().strip()
    try:
        payload = _patterns_payload(kind)
    except ContextError as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for key, value in payload.items():
        if isinstance(value, list):
            table.add_row(key, "\n".join(f"- {item}" for item in value))
        else:
            table.add_row(key, str(value))
    console.print(table)


@app.command("cookbook")
def cookbook(
    kind: str = typer.Argument("service", help="Cookbook kind. Currently: service."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return Codex-friendly cookbook docs for repeated service work."""
    output = output.lower().strip()
    try:
        payload = _cookbook_payload(project_root, kind)
    except ContextError as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Doc", style="bold")
    table.add_column("Headings")
    for doc in payload["docs"]:
        table.add_row(doc["path"], "\n".join(doc.get("headings", [])))
    console.print(table)


@app.command("requirements")
def requirements(
    domain: str = typer.Argument(..., help="Domain key, such as invoice."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    requirements_file: Optional[Path] = typer.Option(None, "--requirements-file", help="Optional requirements JSON file."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return explicit configured domain requirements."""
    output = output.lower().strip()
    try:
        payload = _requirements_payload(project_root, domain, requirements_file)
    except json.JSONDecodeError as exc:
        error_console.print(f"[bold red]Error:[/bold red] invalid requirements JSON: {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Category")
    table.add_column("Requirement")
    table.add_column("Hint")
    for item in payload["requirements"]:
        table.add_row(item["category"], item["requirement"], item["implementation_hint"])
    console.print(table)


@app.command("evidence")
def evidence(
    kind: str = typer.Argument(..., help="Evidence kind: request, domain, service, or model."),
    value: str = typer.Argument(..., help="Request text, domain key, or service name."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return source evidence and likely related contracts for a request/domain/service."""
    output = output.lower().strip()
    kind = kind.lower().strip()
    try:
        inventories = _load_inventories(project_root)
        if kind == "model":
            payload = _model_evidence_payload(project_root, value)
        elif kind == "request":
            domain = _domain_key(value)
            reqs = _domain_requirements(domain, value, _default_requirements_path(project_root.resolve()))
            related = _related_contracts(inventories, value, reqs)
            owner = _recommended_owner(domain, related)
        elif kind == "domain":
            domain = value
            reqs = _domain_requirements(domain, f"create {domain} service", _default_requirements_path(project_root.resolve()))
            related = _related_contracts(inventories, f"create {domain} service", reqs)
            owner = _recommended_owner(domain, related)
        elif kind == "service":
            domain = value
            reqs = []
            related = []
            owner = RecommendedOwner(service_project=value, path=f"services-repo/services/{value}", recommendation="inspect_existing_service", reason="Service evidence requested directly.")
        else:
            raise ContextError("Unknown evidence kind. Use request, domain, service, or model.")
        if kind != "model":
            payload = {
                "kind": kind,
                "value": value,
                "domain": domain,
                "recommended_owner": owner.model_dump(),
                "domain_requirements": [item.model_dump() for item in reqs],
                "related_contracts": [item.model_dump() for item in related],
                "source_evidence": [item.model_dump() for item in _source_evidence(project_root, owner, related)],
            }
    except (ContextError, json.JSONDecodeError) as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Evidence")
    table.add_column("Finding")
    if kind == "model":
        table.add_row("found", str(payload["found"]))
        table.add_row("proto messages", str(len(payload["proto_messages"])))
        table.add_row("service methods", str(len(payload["service_methods"])))
    else:
        for item in payload["source_evidence"]:
            table.add_row(item["path"], item["finding"])
    console.print(table)


@app.command("verify")
def verify(
    service: str = typer.Argument("ceerat-user-service", help="Service project name, or scope: contract-and-service."),
    target: Optional[str] = typer.Argument(None, help="Target for scoped verification, such as service.ServiceManager."),
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
) -> None:
    """Return verification commands Codex should run after service changes."""
    output = output.lower().strip()
    if service == "contract-and-service":
        payload = _verification_contract_and_service_payload(target or "service.ServiceManager")
    else:
        payload = _verification_payload(service)
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Command")
    table.add_column("Purpose")
    for item in payload["commands"]:
        command = item["command"]
        if item.get("workdir"):
            command = f"{item['workdir']}: {command}"
        table.add_row(command, item["purpose"])
    console.print(table)


@app.command("codex-context")
def codex_context(
    output: str = typer.Option("json", "--output", "-o", help="Output format: json or table."),
    project_root: Path = typer.Option(Path("."), "--project-root", help="Builder repo root."),
) -> None:
    """Return the standard context packet Codex should load before backend service work."""
    output = output.lower().strip()
    payload = _codex_context_payload(project_root)
    if output == "json":
        _print_json(payload)
        return
    if output != "table":
        error_console.print("[bold red]Error:[/bold red] --output must be json or table")
        raise typer.Exit(code=2)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Area")
    table.add_column("Items")
    for key, value in payload.items():
        if isinstance(value, list):
            table.add_row(key, "\n".join(f"- {item}" for item in value))
        elif isinstance(value, dict):
            table.add_row(key, "\n".join(f"{k}: {v}" for k, v in value.items()))
        else:
            table.add_row(key, str(value))
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
