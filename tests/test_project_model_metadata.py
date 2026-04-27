"""Tests for model metadata in project config and propagation."""

import tempfile
from pathlib import Path

import yaml

from snowl.project_config import load_project_config


def _write_project(tmp: Path, models: list[dict]) -> Path:
    config = {
        "project": {"name": "test", "root_dir": "."},
        "provider": {
            "id": "test",
            "kind": "openai_compatible",
            "base_url": "https://api.test.com/v1",
            "api_key": "sk-test",
        },
        "agent_matrix": {"models": models},
        "eval": {
            "benchmark": "strongreject",
            "code": {
                "base_dir": ".",
                "task_module": "./task.py",
                "agent_module": "./agent.py",
                "scorer_module": "./scorer.py",
            },
        },
    }
    # Create stub code files so validation passes
    for name in ("task.py", "agent.py", "scorer.py"):
        (tmp / name).write_text("# stub\n", encoding="utf-8")
    p = tmp / "project.yml"
    p.write_text(yaml.dump(config), encoding="utf-8")
    return p


class TestModelMetadataParsing:
    def test_no_metadata(self, tmp_path: Path):
        p = _write_project(tmp_path, [{"id": "m1", "model": "test-model"}])
        config = load_project_config(p)
        assert config.models[0].metadata is None

    def test_metadata_with_company(self, tmp_path: Path):
        p = _write_project(tmp_path, [
            {"id": "m1", "model": "test-model", "metadata": {"company": "OpenAI"}},
        ])
        config = load_project_config(p)
        assert config.models[0].metadata is not None
        assert config.models[0].metadata["company"] == "OpenAI"

    def test_metadata_with_source_type(self, tmp_path: Path):
        p = _write_project(tmp_path, [
            {"id": "m1", "model": "test-model", "metadata": {"source_type": "closed_source"}},
        ])
        config = load_project_config(p)
        assert config.models[0].metadata["source_type"] == "closed_source"

    def test_metadata_with_reasoning(self, tmp_path: Path):
        p = _write_project(tmp_path, [
            {"id": "m1", "model": "test-model", "metadata": {"reasoning": "high"}},
        ])
        config = load_project_config(p)
        assert config.models[0].metadata["reasoning"] == "high"

    def test_invalid_source_type_rejected(self, tmp_path: Path):
        p = _write_project(tmp_path, [
            {"id": "m1", "model": "test-model", "metadata": {"source_type": "invalid"}},
        ])
        try:
            load_project_config(p)
            assert False, "Should have raised"
        except Exception as e:
            assert "source_type" in str(e)

    def test_invalid_reasoning_rejected(self, tmp_path: Path):
        p = _write_project(tmp_path, [
            {"id": "m1", "model": "test-model", "metadata": {"reasoning": "extreme"}},
        ])
        try:
            load_project_config(p)
            assert False, "Should have raised"
        except Exception as e:
            assert "reasoning" in str(e)

    def test_all_metadata_fields(self, tmp_path: Path):
        p = _write_project(tmp_path, [
            {
                "id": "m1",
                "model": "gpt-5",
                "metadata": {
                    "company": "OpenAI",
                    "country": "US",
                    "source_type": "closed_source",
                    "license_type": "proprietary",
                    "reasoning": "high",
                    "model_family": "GPT-5",
                },
            },
        ])
        config = load_project_config(p)
        meta = config.models[0].metadata
        assert meta is not None
        assert meta["company"] == "OpenAI"
        assert meta["country"] == "US"
        assert meta["source_type"] == "closed_source"
        assert meta["reasoning"] == "high"
        assert meta["model_family"] == "GPT-5"

    def test_multiple_models_with_metadata(self, tmp_path: Path):
        p = _write_project(tmp_path, [
            {"id": "m1", "model": "model-a", "metadata": {"company": "A", "source_type": "open_source"}},
            {"id": "m2", "model": "model-b", "metadata": {"company": "B", "source_type": "closed_source"}},
        ])
        config = load_project_config(p)
        assert len(config.models) == 2
        assert config.models[0].metadata["company"] == "A"
        assert config.models[1].metadata["company"] == "B"
