from __future__ import annotations

from ceerat_builder.context_loader import AgentContext
from ceerat_builder.models import ImplementationPlan
from ceerat_builder.openai_client import CeeratOpenAIClient


def build_plan(
    *,
    client: CeeratOpenAIClient,
    context: AgentContext,
    user_request: str,
) -> ImplementationPlan:
    return client.create_plan(
        system_prompt=context.system_prompt,
        planner_prompt=context.planner_prompt,
        architecture_context=context.architecture_context,
        user_request=user_request,
    )
