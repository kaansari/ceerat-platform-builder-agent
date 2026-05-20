from __future__ import annotations

from typing import List

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
