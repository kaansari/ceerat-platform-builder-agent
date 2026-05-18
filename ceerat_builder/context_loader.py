from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ContextError(RuntimeError):
    """Raised when Ceerat agent context cannot be loaded."""


ARCHITECTURE_DOCS = [
    "architecture.md",
    "module-generation-standard.md",
    "security-rbac-standard.md",
    "ui-standard.md",
    "ai-tool-standard.md",
]

PROMPTS = [
    "prompts/system.md",
    "prompts/planner.md",
]


@dataclass(frozen=True)
class AgentContext:
    architecture_context: str
    system_prompt: str
    planner_prompt: str


def _read_required_file(path: Path) -> str:
    if not path.is_file():
        raise ContextError(f"Missing required architecture doc: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ContextError(f"Required architecture doc is empty: {path}")
    return content


def load_agent_context(project_root: Path) -> AgentContext:
    agent_dir = project_root / ".ceerat-agent"
    if not agent_dir.is_dir():
        raise ContextError(f"Missing architecture docs directory: {agent_dir}")

    docs = []
    for relative in ARCHITECTURE_DOCS:
        path = agent_dir / relative
        docs.append(f"# {relative}\n\n{_read_required_file(path)}")

    prompt_contents = {
        relative: _read_required_file(agent_dir / relative) for relative in PROMPTS
    }

    return AgentContext(
        architecture_context="\n\n---\n\n".join(docs),
        system_prompt=prompt_contents["prompts/system.md"],
        planner_prompt=prompt_contents["prompts/planner.md"],
    )
