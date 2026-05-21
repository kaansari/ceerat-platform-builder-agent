from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ImplementationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_name: str = Field(description="Human-readable module name.")
    business_objects: List[str] = Field(description="Business objects and relationships.")
    required_protos: List[str] = Field(description="Required protobuf messages and RPCs.")
    required_services: List[str] = Field(description="Required backend service handlers, repositories, admin hooks, startup wiring, and config.")
    required_database_migrations: List[str] = Field(description="Required OLTP database objects, migrations, indexes, constraints, seed data, and BI/event store notes.")
    required_rbac_permissions: List[str] = Field(description="Required security, RBAC, public method, admin-only, and ownership checks.")
    required_logging_events: List[str] = Field(description="Required structured logs, business events, redaction, and observability behavior.")
    integration_impact: List[str] = Field(description="Existing app, agent, infra, or caller impacts to coordinate, without designing frontend UI.")
    required_tests: List[str] = Field(description="Required test coverage.")
    risks_questions: List[str] = Field(description="Risks, questions, and open decisions.")


class InventoryMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Inventory source, such as contracts, services, or apps.")
    name: str = Field(description="Matched package, service, route, tool, or component name.")
    path: str = Field(description="Relevant source path when available.")
    reason: str = Field(description="Why this inventory item matched the request.")


class RecommendedOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_project: str = Field(description="Recommended service project or new-service placeholder.")
    path: str = Field(description="Recommended owner path.")
    recommendation: str = Field(description="Extend existing service or create a new service.")
    reason: str = Field(description="Why this owner is recommended.")


class RelatedContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str = Field(description="Proto package name.")
    service: str = Field(description="Full gRPC service name.")
    proto_path: str = Field(description="Path to the proto file.")
    domain: str = Field(description="Domain description from inventory.")
    rpcs: List[str] = Field(description="Existing RPC names.")
    messages: List[str] = Field(description="Existing message names.")
    reason: str = Field(description="Why this contract is relevant.")


class SuggestedRPC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Suggested RPC name.")
    full_method: str = Field(description="Suggested full gRPC method name.")
    request: str = Field(description="Suggested request message.")
    response: str = Field(description="Suggested response message.")
    purpose: str = Field(description="Purpose of the RPC.")


class SuggestedContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str = Field(description="Suggested proto package.")
    service: str = Field(description="Suggested gRPC service.")
    proto_path: str = Field(description="Suggested proto path.")
    rpcs: List[SuggestedRPC] = Field(description="Suggested RPCs.")
    messages: List[str] = Field(description="Suggested message names.")


class SuggestedDatabaseObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Suggested table/object name.")
    purpose: str = Field(description="What this object stores.")
    key_columns: List[str] = Field(description="Important columns.")
    relationships: List[str] = Field(description="Foreign keys or logical relationships.")
    indexes: List[str] = Field(description="Suggested indexes or constraints.")


class SuggestedServiceSkeleton(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_project: str = Field(description="Service project to modify or create.")
    packages: List[str] = Field(description="Go packages/modules to add or update.")
    files: List[str] = Field(description="Suggested files to add or update.")
    startup_wiring: List[str] = Field(description="Startup/registration wiring to add.")


class SuggestedRBACPermission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = Field(description="Full gRPC method.")
    default_roles: List[str] = Field(description="Suggested default roles.")
    public: bool = Field(description="Whether this should be public.")
    ownership_rule: str = Field(description="Required handler/repository ownership rule.")


class DomainRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Where the requirement came from, such as request text or a domain requirements file.")
    category: str = Field(description="Requirement category, such as relationship, field, rule, or workflow.")
    name: Optional[str] = Field(default=None, description="Optional stable field, relationship, rule, or workflow name from the requirements source.")
    requirement: str = Field(description="The business or data requirement Codex must preserve.")
    implementation_hint: str = Field(description="Concrete implementation guidance for Codex to evaluate.")


class SourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(description="Evidence category, such as service wiring, repository pattern, security, or docs.")
    path: str = Field(description="Source file or doc path.")
    symbols: List[str] = Field(description="Relevant symbols, functions, packages, tables, or declarations found.")
    finding: str = Field(description="Concrete fact discovered from source files or inventories.")


class PlanningPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(description="Original user request.")
    mode: str = Field(description="Packet mode. Local packets are prepared for Codex reasoning.")
    codex_task: str = Field(description="Instruction to Codex for producing the actual implementation plan or code.")
    detected_domain: str = Field(description="Domain inferred from the request.")
    recommended_owner: RecommendedOwner = Field(description="Recommended service owner.")
    inventory_matches: List[InventoryMatch] = Field(description="Relevant inventory matches.")
    related_contracts: List[RelatedContract] = Field(description="Relevant existing contracts expanded from inventory.")
    domain_requirements: List[DomainRequirement] = Field(description="Business requirements and must-have fields/relationships extracted from request or configured domain requirements.")
    source_evidence: List[SourceEvidence] = Field(description="Concrete source facts Codex should use before making implementation decisions.")
    suggested_contract: SuggestedContract = Field(description="Suggested contract skeleton for Codex to evaluate.")
    suggested_database_objects: List[SuggestedDatabaseObject] = Field(description="Suggested database skeleton for Codex to evaluate.")
    suggested_service_skeleton: SuggestedServiceSkeleton = Field(description="Suggested service implementation skeleton for Codex to evaluate.")
    suggested_rbac_permissions: List[SuggestedRBACPermission] = Field(description="Suggested RBAC method permissions for Codex to evaluate.")
    relevant_contracts: List[str] = Field(description="Relevant contract packages, services, methods, or docs.")
    relevant_services: List[str] = Field(description="Relevant backend service projects, gRPC services, docs, or patterns.")
    relevant_database: List[str] = Field(description="Database ownership and migration context Codex should use.")
    relevant_security: List[str] = Field(description="Security, RBAC, public method, and ownership context.")
    relevant_apps_or_callers: List[str] = Field(description="Existing app or AI callers for compatibility only, not UI design.")
    standards_to_apply: List[str] = Field(description="Ceerat standards Codex must follow.")
    required_output_from_codex: List[str] = Field(description="What Codex should return after reasoning over this packet.")
    warnings: List[str] = Field(description="Important caveats and scope warnings.")
