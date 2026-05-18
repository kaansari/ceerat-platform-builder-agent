from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ImplementationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_name: str = Field(description="Human-readable module name.")
    business_objects: list[str] = Field(description="Business objects and relationships.")
    required_protos: list[str] = Field(description="Required protobuf messages and RPCs.")
    required_services: list[str] = Field(description="Required backend services.")
    required_database_migrations: list[str] = Field(description="Required database migrations.")
    required_ui_pages: list[str] = Field(description="Required UI pages and workflows.")
    required_rbac_permissions: list[str] = Field(description="Required RBAC permissions.")
    required_ai_agent_tools: list[str] = Field(description="Required AI agent tools.")
    required_tests: list[str] = Field(description="Required test coverage.")
    risks_questions: list[str] = Field(description="Risks, questions, and open decisions.")
