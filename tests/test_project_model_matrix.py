from __future__ import annotations

from pathlib import Path

import pytest

from snowl.agents import build_model_variants
from snowl.errors import SnowlValidationError
from snowl.model import load_project_model_matrix
from snowl.project_config import load_project_config


def _touch_eval_files(tmp_path: Path) -> None:
    for name in ("task.py", "agent.py", "scorer.py"):
        (tmp_path / name).write_text("# test\n", encoding="utf-8")


def test_load_project_model_matrix_parses_provider_models_and_judge(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
  timeout: 9
  max_retries: 3
agent_matrix:
  models:
    - id: alpha
      model: gpt-4o-mini
    - id: beta
      model: Qwen/Qwen3-32B
judge:
  model: gpt-4.1-mini
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
        """,
        encoding="utf-8",
    )
    _touch_eval_files(tmp_path)

    matrix = load_project_model_matrix(tmp_path)
    project = load_project_config(tmp_path)
    assert project.provider.id == "demo"
    assert matrix.provider.kind == "openai_compatible"
    assert matrix.provider.base_url == "https://example.com/v1"
    assert [entry.id for entry in matrix.models] == ["alpha", "beta"]
    assert [entry.model for entry in matrix.models] == ["gpt-4o-mini", "Qwen/Qwen3-32B"]
    assert matrix.judge is not None
    assert matrix.judge.model == "gpt-4.1-mini"


def test_load_project_model_matrix_requires_non_empty_agent_matrix(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
agent_matrix:
  models: []
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
        """,
        encoding="utf-8",
    )
    _touch_eval_files(tmp_path)

    with pytest.raises(SnowlValidationError, match="agent_matrix.models"):
        load_project_model_matrix(tmp_path)


def test_load_project_model_matrix_rejects_duplicate_model_ids(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
agent_matrix:
  models:
    - id: repeated
      model: gpt-4o-mini
    - id: repeated
      model: Qwen/Qwen3-32B
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
        """,
        encoding="utf-8",
    )
    _touch_eval_files(tmp_path)

    with pytest.raises(SnowlValidationError, match="Duplicate agent_matrix model id"):
        load_project_model_matrix(tmp_path)


def test_build_model_variants_uses_declared_variant_ids(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
  timeout: 7
  max_retries: 1
agent_matrix:
  models:
    - id: alpha
      model: gpt-4o-mini
    - id: beta
      model: Qwen/Qwen3-32B
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
        """,
        encoding="utf-8",
    )
    _touch_eval_files(tmp_path)

    class _Agent:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        async def run(self, state, context, tools=None):  # type: ignore[no-untyped-def]
            _ = context, tools
            return state

    variants = build_model_variants(
        base_dir=tmp_path,
        agent_id="demo_agent",
        factory=lambda entry, _provider: _Agent(entry.model),
    )

    assert [variant.variant_id for variant in variants] == ["alpha", "beta"]
    assert [variant.model for variant in variants] == ["gpt-4o-mini", "Qwen/Qwen3-32B"]
    assert variants[0].params["timeout"] == 7.0
    assert variants[1].provenance["provider"] == "openai_compatible"


def test_project_config_allows_zero_container_slots(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
agent_matrix:
  models:
    - id: alpha
      model: gpt-4o-mini
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
runtime:
  max_container_slots: 0
        """,
        encoding="utf-8",
    )
    _touch_eval_files(tmp_path)

    project = load_project_config(tmp_path)
    assert project.runtime.max_container_slots == 0
