from __future__ import annotations

import json

from openai import OpenAI, OpenAIError

from ceerat_builder.models import ImplementationPlan


class OpenAIClientError(RuntimeError):
    """Raised when OpenAI cannot produce a plan."""


class CeeratOpenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def create_plan(
        self,
        *,
        system_prompt: str,
        planner_prompt: str,
        architecture_context: str,
        user_request: str,
    ) -> ImplementationPlan:
        schema = ImplementationPlan.model_json_schema()
        user_content = (
            f"{planner_prompt}\n\n"
            "Ceerat architecture context:\n"
            f"{architecture_context}\n\n"
            "User request:\n"
            f"{user_request}"
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "implementation_plan",
                        "schema": schema,
                        "strict": True,
                    },
                },
            )
        except OpenAIError as exc:
            raise OpenAIClientError(f"OpenAI API failure: {exc}") from exc

        message = response.choices[0].message.content
        if not message:
            raise OpenAIClientError("OpenAI returned an empty response.")

        try:
            return ImplementationPlan.model_validate(json.loads(message))
        except (json.JSONDecodeError, ValueError) as exc:
            raise OpenAIClientError("OpenAI returned an invalid plan payload.") from exc
