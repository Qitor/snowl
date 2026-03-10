"""Helpers for building multi-model AgentVariant matrices from project config."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from snowl.core import AgentVariant, make_agent_variant
from snowl.model import ProjectModelEntry, ProjectProviderConfig, load_project_model_matrix


ModelVariantFactory = Callable[[ProjectModelEntry, ProjectProviderConfig], Any]


def build_model_variants(
    *,
    base_dir: str | Path,
    agent_id: str,
    factory: ModelVariantFactory,
) -> list[AgentVariant]:
    base_path = Path(base_dir).resolve()
    matrix = load_project_model_matrix(base_path)
    source_path = base_path / "model.yml"
    if not source_path.exists():
        source_path = base_path / "model.yaml"
    variants: list[AgentVariant] = []
    for entry in matrix.models:
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
                    "base_url": matrix.provider.base_url,
                },
            )
        )
    return variants
