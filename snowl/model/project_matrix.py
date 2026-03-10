"""Project-level model matrix configuration for multi-model authoring."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml

from snowl.errors import SnowlValidationError
from snowl.model.openai_compatible import OpenAICompatibleConfig


@dataclass(frozen=True)
class ProjectProviderConfig:
    kind: str
    base_url: str
    api_key: str
    timeout: float
    max_retries: int


@dataclass(frozen=True)
class ProjectModelEntry:
    id: str
    model: str
    config: OpenAICompatibleConfig


@dataclass(frozen=True)
class ProjectJudgeConfig:
    model: str
    config: OpenAICompatibleConfig


@dataclass(frozen=True)
class ProjectModelMatrix:
    provider: ProjectProviderConfig
    models: list[ProjectModelEntry]
    judge: ProjectJudgeConfig | None = None


def _find_model_file(base_dir: Path) -> Path | None:
    for name in ("model.yml", "model.yaml"):
        path = base_dir / name
        if path.exists():
            return path
    return None


def _require_mapping(value: Any, *, label: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnowlValidationError(f"{label} must be a mapping in {path}")
    return dict(value)


def _require_non_empty_str(value: Any, *, label: str, path: Path) -> str:
    text = str(value or "").strip()
    if not text:
        raise SnowlValidationError(f"{label} must be a non-empty string in {path}")
    return text


def _coerce_timeout(value: Any, *, path: Path) -> float:
    try:
        timeout = float(value if value is not None else 30.0)
    except Exception as exc:
        raise SnowlValidationError(f"provider.timeout must be numeric in {path}") from exc
    if timeout <= 0:
        raise SnowlValidationError(f"provider.timeout must be > 0 in {path}")
    return timeout


def _coerce_max_retries(value: Any, *, path: Path) -> int:
    try:
        retries = int(value if value is not None else 2)
    except Exception as exc:
        raise SnowlValidationError(f"provider.max_retries must be an integer in {path}") from exc
    if retries < 0:
        raise SnowlValidationError(f"provider.max_retries must be >= 0 in {path}")
    return retries


def load_project_model_matrix(base_dir: str | Path) -> ProjectModelMatrix:
    base_path = Path(base_dir).resolve()
    model_file = _find_model_file(base_path)
    if model_file is None:
        raise SnowlValidationError(f"Missing model.yml in {base_path}")

    try:
        raw = yaml.safe_load(model_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise SnowlValidationError(f"Failed to parse model config: {model_file}: {exc}") from exc
    data = _require_mapping(raw, label="model config", path=model_file)

    provider_data = _require_mapping(data.get("provider"), label="provider", path=model_file)
    provider_kind = _require_non_empty_str(provider_data.get("kind"), label="provider.kind", path=model_file)
    if provider_kind != "openai_compatible":
        raise SnowlValidationError(
            f"Unsupported provider.kind '{provider_kind}' in {model_file}; only openai_compatible is supported."
        )

    provider = ProjectProviderConfig(
        kind=provider_kind,
        base_url=_require_non_empty_str(provider_data.get("base_url"), label="provider.base_url", path=model_file),
        api_key=_require_non_empty_str(provider_data.get("api_key"), label="provider.api_key", path=model_file),
        timeout=_coerce_timeout(provider_data.get("timeout"), path=model_file),
        max_retries=_coerce_max_retries(provider_data.get("max_retries"), path=model_file),
    )

    matrix_data = _require_mapping(data.get("agent_matrix"), label="agent_matrix", path=model_file)
    models_raw = matrix_data.get("models")
    if not isinstance(models_raw, list) or not models_raw:
        raise SnowlValidationError(f"agent_matrix.models must be a non-empty list in {model_file}")

    seen_ids: set[str] = set()
    seen_models: set[str] = set()
    models: list[ProjectModelEntry] = []
    for index, item in enumerate(models_raw, start=1):
        row = _require_mapping(item, label=f"agent_matrix.models[{index}]", path=model_file)
        model_id = _require_non_empty_str(row.get("id"), label=f"agent_matrix.models[{index}].id", path=model_file)
        model_name = _require_non_empty_str(
            row.get("model"),
            label=f"agent_matrix.models[{index}].model",
            path=model_file,
        )
        if model_id in seen_ids:
            raise SnowlValidationError(f"Duplicate agent_matrix model id '{model_id}' in {model_file}")
        if model_name in seen_models:
            raise SnowlValidationError(f"Duplicate agent_matrix model '{model_name}' in {model_file}")
        seen_ids.add(model_id)
        seen_models.add(model_name)
        models.append(
            ProjectModelEntry(
                id=model_id,
                model=model_name,
                config=OpenAICompatibleConfig(
                    base_url=provider.base_url,
                    api_key=provider.api_key,
                    model=model_name,
                    timeout=provider.timeout,
                    max_retries=provider.max_retries,
                ),
            )
        )

    judge_data = data.get("judge")
    judge: ProjectJudgeConfig | None = None
    if judge_data is not None:
        judge_row = _require_mapping(judge_data, label="judge", path=model_file)
        judge_model = _require_non_empty_str(judge_row.get("model"), label="judge.model", path=model_file)
        judge = ProjectJudgeConfig(
            model=judge_model,
            config=OpenAICompatibleConfig(
                base_url=provider.base_url,
                api_key=provider.api_key,
                model=judge_model,
                timeout=provider.timeout,
                max_retries=provider.max_retries,
            ),
        )

    return ProjectModelMatrix(provider=provider, models=models, judge=judge)


def apply_project_judge_env(base_dir: str | Path) -> dict[str, str]:
    matrix = load_project_model_matrix(base_dir)
    applied = {
        "OPENAI_BASE_URL": matrix.provider.base_url,
        "OPENAI_API_KEY": matrix.provider.api_key,
        "OPENAI_TIMEOUT": str(matrix.provider.timeout),
        "OPENAI_MAX_RETRIES": str(matrix.provider.max_retries),
    }
    if matrix.judge is not None:
        applied["OPENAI_MODEL"] = matrix.judge.model
    for key, value in applied.items():
        os.environ[key] = value
    return applied
