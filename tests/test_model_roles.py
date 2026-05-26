"""Tests for ModelRole, ModelAssignment, ModelRoleRegistry, and config parsing."""

import pytest

from snowl.core.model_roles import (
    ModelAssignment,
    ModelRole,
    ModelRoleRegistry,
    model_assignments_from_config,
)
from snowl.errors import SnowlValidationError


# ---------------------------------------------------------------------------
# ModelRole
# ---------------------------------------------------------------------------

class TestModelRole:
    def test_values(self):
        assert ModelRole.AGENT.value == "agent"
        assert ModelRole.JUDGE.value == "judge"
        assert ModelRole.ATTACKER.value == "attacker"
        assert ModelRole.TARGET.value == "target"

    def test_from_string(self):
        assert ModelRole("agent") is ModelRole.AGENT

    def test_invalid_role(self):
        with pytest.raises(ValueError):
            ModelRole("nonexistent")


# ---------------------------------------------------------------------------
# ModelAssignment
# ---------------------------------------------------------------------------

class TestModelAssignment:
    def test_creation(self):
        ma = ModelAssignment(role=ModelRole.AGENT, model="gpt-4o")
        assert ma.role is ModelRole.AGENT
        assert ma.model == "gpt-4o"

    def test_with_params(self):
        ma = ModelAssignment(
            role=ModelRole.JUDGE,
            model="claude-3.5",
            provider_id="anthropic",
            params={"temperature": 0.0},
        )
        assert ma.provider_id == "anthropic"
        assert ma.params["temperature"] == 0.0

    def test_rejects_invalid_role(self):
        with pytest.raises(SnowlValidationError, match="ModelRole"):
            ModelAssignment(role="not_a_role", model="gpt-4o")

    def test_rejects_empty_model(self):
        with pytest.raises(SnowlValidationError, match="non-empty"):
            ModelAssignment(role=ModelRole.AGENT, model="")

    def test_rejects_whitespace_model(self):
        with pytest.raises(SnowlValidationError, match="non-empty"):
            ModelAssignment(role=ModelRole.AGENT, model="   ")

    def test_frozen(self):
        ma = ModelAssignment(role=ModelRole.AGENT, model="gpt-4o")
        with pytest.raises(AttributeError):
            ma.model = "claude"


# ---------------------------------------------------------------------------
# ModelRoleRegistry
# ---------------------------------------------------------------------------

class TestModelRoleRegistry:
    def test_empty_registry(self):
        reg = ModelRoleRegistry()
        assert reg.resolve(ModelRole.AGENT) is None
        assert reg.assigned_roles() == []

    def test_assign_and_resolve(self):
        reg = ModelRoleRegistry()
        reg.assign(ModelAssignment(role=ModelRole.AGENT, model="gpt-4o"))
        assert reg.resolve(ModelRole.AGENT) == "gpt-4o"

    def test_resolve_with_default(self):
        reg = ModelRoleRegistry()
        assert reg.resolve(ModelRole.AGENT, default="fallback") == "fallback"

    def test_overwrite_assignment(self):
        reg = ModelRoleRegistry()
        reg.assign(ModelAssignment(role=ModelRole.AGENT, model="gpt-4o"))
        reg.assign(ModelAssignment(role=ModelRole.AGENT, model="claude-3.5"))
        assert reg.resolve(ModelRole.AGENT) == "claude-3.5"

    def test_multiple_roles(self):
        reg = ModelRoleRegistry()
        reg.assign(ModelAssignment(role=ModelRole.AGENT, model="gpt-4o"))
        reg.assign(ModelAssignment(role=ModelRole.JUDGE, model="claude-3.5"))
        assert reg.assigned_roles() == [ModelRole.AGENT, ModelRole.JUDGE]

    def test_get_assignment(self):
        reg = ModelRoleRegistry()
        ma = ModelAssignment(role=ModelRole.AGENT, model="gpt-4o", provider_id="openai")
        reg.assign(ma)
        result = reg.get_assignment(ModelRole.AGENT)
        assert result is ma
        assert result.provider_id == "openai"

    def test_get_assignment_not_found(self):
        reg = ModelRoleRegistry()
        assert reg.get_assignment(ModelRole.JUDGE) is None

    def test_all_assignments(self):
        reg = ModelRoleRegistry()
        reg.assign(ModelAssignment(role=ModelRole.AGENT, model="gpt-4o"))
        reg.assign(ModelAssignment(role=ModelRole.JUDGE, model="claude-3.5"))
        assert len(reg.all_assignments()) == 2

    def test_clear(self):
        reg = ModelRoleRegistry()
        reg.assign(ModelAssignment(role=ModelRole.AGENT, model="gpt-4o"))
        reg.clear()
        assert reg.assigned_roles() == []


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

class TestModelAssignmentsFromConfig:
    def test_parse_full_config(self):
        config = {
            "models": {
                "agent": {"model": "gpt-4o", "provider_id": "openai"},
                "judge": {"model": "claude-3.5", "params": {"temperature": 0.0}},
            }
        }
        reg = model_assignments_from_config(config)
        assert reg.resolve(ModelRole.AGENT) == "gpt-4o"
        assert reg.resolve(ModelRole.JUDGE) == "claude-3.5"
        assert reg.get_assignment(ModelRole.AGENT).provider_id == "openai"
        assert reg.get_assignment(ModelRole.JUDGE).params == {"temperature": 0.0}

    def test_empty_config(self):
        reg = model_assignments_from_config({})
        assert reg.assigned_roles() == []

    def test_no_models_key(self):
        reg = model_assignments_from_config({"other": "data"})
        assert reg.assigned_roles() == []

    def test_skips_unknown_roles(self):
        config = {
            "models": {
                "agent": {"model": "gpt-4o"},
                "interpreter": {"model": "code-llama"},
            }
        }
        reg = model_assignments_from_config(config)
        assert reg.assigned_roles() == [ModelRole.AGENT]

    def test_skips_empty_model(self):
        config = {
            "models": {
                "agent": {"model": ""},
                "judge": {"model": "claude-3.5"},
            }
        }
        reg = model_assignments_from_config(config)
        assert reg.assigned_roles() == [ModelRole.JUDGE]

    def test_skips_non_mapping_config(self):
        config = {"models": "not_a_mapping"}
        reg = model_assignments_from_config(config)
        assert reg.assigned_roles() == []
