"""Project-matrix expansion helper that builds `AgentVariant` objects from `project.yml`.

Framework role:
- Reads provider/model matrix, instantiates per-model agent instances via user factory, and attaches variant provenance.
- Produces variant metadata (`variant_id`, model, provider details) consumed by planning, artifacts, and compare views.

Runtime/usage wiring:
- Used during eval/bootstrap when agent declarations opt into model-matrix expansion.

Change guardrails:
- Keep provenance fields and variant ids deterministic; downstream rerun/recovery logic relies on stable identities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from snowl.core import AgentVariant, make_agent_variant
from snowl.model import ProjectModelEntry, ProjectProviderConfig, find_project_file, load_project_model_matrix


ModelVariantFactory = Callable[[ProjectModelEntry, ProjectProviderConfig], Any]


def build_model_variants(
    *,
    base_dir: str | Path,
    agent_id: str,
    factory: ModelVariantFactory,
) -> list[AgentVariant]:
    base_path = Path(base_dir).resolve()
    matrix = load_project_model_matrix(base_path)
    source_path = find_project_file(base_path) or (base_path / "project.yml")
    variants: list[AgentVariant] = []
    for entry in matrix.agent_matrix:
        agent = factory(entry, matrix.provider)
        try:
            setattr(agent, "agent_id", agent_id)
        except Exception:
            pass
        try:
            setattr(agent, "variant_id", entry.id)
        except Exception:
            pass
        try:
            setattr(agent, "model", entry.model)
        except Exception:
            pass
        variants.append(
            make_agent_variant(
                agent=agent,
                agent_id=agent_id,
                variant_id=entry.id,
                model=entry.model,
                params={
                    "model": entry.model,
                    "timeout": entry.config.timeout,
                    "max_retries": entry.config.max_retries,
                },
                provenance={
                    "source": str(source_path),
                    "provider": matrix.provider.kind,
                    "provider_id": matrix.provider.id,
                    "base_url": matrix.provider.base_url,
                },
            )
        )
    return variants
