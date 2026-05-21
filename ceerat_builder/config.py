from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_MODEL = "gpt-4.1-mini"


class ConfigError(RuntimeError):
    """Raised when the CLI cannot load required configuration."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    project_root: Path


def load_ai_settings(project_root: Optional[Path] = None) -> Settings:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. It is required only for `ceerat-builder plan --mode ai`."
        )

    return Settings(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        project_root=(project_root or Path.cwd()).resolve(),
    )
