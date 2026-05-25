"""Tests for VerifierMode, VerifierSpec, validation, and verifier_spec_from_config."""

import pytest

from snowl.core.env import (
    VerifierMode,
    VerifierSpec,
    validate_verifier_spec,
)
from snowl.core import Task, EnvSpec
from snowl.errors import SnowlValidationError


# ---------------------------------------------------------------------------
# VerifierMode
# ---------------------------------------------------------------------------

class TestVerifierMode:
    def test_shared_value(self):
        assert VerifierMode.SHARED == "shared"
        assert VerifierMode.SHARED.value == "shared"

    def test_separate_value(self):
        assert VerifierMode.SEPARATE == "separate"
        assert VerifierMode.SEPARATE.value == "separate"

    def test_from_string(self):
        assert VerifierMode("shared") == VerifierMode.SHARED
        assert VerifierMode("separate") == VerifierMode.SEPARATE

    def test_invalid_string(self):
        with pytest.raises(ValueError):
            VerifierMode("invalid")


# ---------------------------------------------------------------------------
# VerifierSpec
# ---------------------------------------------------------------------------

class TestVerifierSpec:
    def test_default_is_shared(self):
        spec = VerifierSpec()
        assert spec.mode == VerifierMode.SHARED
        assert spec.image is None
        assert spec.priority_scorers == ()
        assert spec.timeout_seconds == 120.0

    def test_separate_with_image(self):
        spec = VerifierSpec(mode=VerifierMode.SEPARATE, image="snowl-verifier:latest")
        assert spec.mode == VerifierMode.SEPARATE
        assert spec.image == "snowl-verifier:latest"

    def test_separate_with_build_context(self):
        spec = VerifierSpec(mode=VerifierMode.SEPARATE, build_context="/path/to/build")
        assert spec.build_context == "/path/to/build"

    def test_full_spec(self):
        spec = VerifierSpec(
            mode=VerifierMode.SEPARATE,
            image="verifier:1",
            environment={"API_KEY": "xxx"},
            priority_scorers=("command_check", "workspace_diff"),
            timeout_seconds=60.0,
            metadata={"domain": "security"},
        )
        assert spec.environment == {"API_KEY": "xxx"}
        assert spec.priority_scorers == ("command_check", "workspace_diff")
        assert spec.timeout_seconds == 60.0

    def test_frozen(self):
        spec = VerifierSpec()
        with pytest.raises(AttributeError):
            spec.mode = VerifierMode.SEPARATE

    def test_spec_hash_deterministic(self):
        spec1 = VerifierSpec(mode=VerifierMode.SEPARATE, image="test:1")
        spec2 = VerifierSpec(mode=VerifierMode.SEPARATE, image="test:1")
        assert spec1.spec_hash() == spec2.spec_hash()

    def test_spec_hash_differs_for_different_specs(self):
        spec1 = VerifierSpec(mode=VerifierMode.SEPARATE, image="test:1")
        spec2 = VerifierSpec(mode=VerifierMode.SEPARATE, image="test:2")
        assert spec1.spec_hash() != spec2.spec_hash()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidateVerifierSpec:
    def test_valid_shared(self):
        spec = VerifierSpec(mode=VerifierMode.SHARED)
        validate_verifier_spec(spec)  # no error

    def test_valid_separate_with_image(self):
        spec = VerifierSpec(mode=VerifierMode.SEPARATE, image="test:1")
        validate_verifier_spec(spec)

    def test_valid_separate_with_build_context(self):
        spec = VerifierSpec(mode=VerifierMode.SEPARATE, build_context="/path")
        validate_verifier_spec(spec)

    def test_separate_without_image_or_build_rejected(self):
        spec = VerifierSpec(mode=VerifierMode.SEPARATE)
        with pytest.raises(SnowlValidationError, match="image.*build_context"):
            validate_verifier_spec(spec)

    def test_negative_timeout_rejected(self):
        spec = VerifierSpec(timeout_seconds=-1)
        with pytest.raises(SnowlValidationError, match="timeout"):
            validate_verifier_spec(spec)


# ---------------------------------------------------------------------------
# Task integration
# ---------------------------------------------------------------------------

class TestTaskVerifierSpec:
    def test_default_none(self):
        t = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([]))
        assert t.verifier_spec is None

    def test_with_verifier_spec(self):
        vs = VerifierSpec(mode=VerifierMode.SEPARATE, image="v:1")
        t = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([]), verifier_spec=vs)
        assert t.verifier_spec.mode == VerifierMode.SEPARATE

    def test_validate_task_with_bad_verifier(self):
        vs = VerifierSpec(mode=VerifierMode.SEPARATE)  # no image
        t = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([]), verifier_spec=vs)
        with pytest.raises(SnowlValidationError, match="image.*build_context"):
            from snowl.core.task import validate_task
            validate_task(t)


# ---------------------------------------------------------------------------
# verifier_spec_from_config
# ---------------------------------------------------------------------------

class TestVerifierSpecFromConfig:
    def test_none_returns_none(self):
        from snowl.runtime.separated_verifier import verifier_spec_from_config
        assert verifier_spec_from_config(None) is None

    def test_empty_returns_none(self):
        from snowl.runtime.separated_verifier import verifier_spec_from_config
        assert verifier_spec_from_config({}) is None

    def test_shared_from_config(self):
        from snowl.runtime.separated_verifier import verifier_spec_from_config
        spec = verifier_spec_from_config({"mode": "shared"})
        assert spec is not None
        assert spec.mode == VerifierMode.SHARED

    def test_separate_from_config(self):
        from snowl.runtime.separated_verifier import verifier_spec_from_config
        spec = verifier_spec_from_config({
            "mode": "separate",
            "image": "verifier:latest",
            "priority_scorers": ["command_check"],
            "timeout_seconds": 60,
        })
        assert spec.mode == VerifierMode.SEPARATE
        assert spec.image == "verifier:latest"
        assert spec.priority_scorers == ("command_check",)
        assert spec.timeout_seconds == 60.0

    def test_invalid_mode_rejected(self):
        from snowl.runtime.separated_verifier import verifier_spec_from_config
        with pytest.raises(SnowlValidationError, match="mode"):
            verifier_spec_from_config({"mode": "invalid"})

    def test_separate_without_image_rejected(self):
        from snowl.runtime.separated_verifier import verifier_spec_from_config
        with pytest.raises(SnowlValidationError, match="image.*build_context"):
            verifier_spec_from_config({"mode": "separate"})

    def test_command_string_normalized(self):
        from snowl.runtime.separated_verifier import verifier_spec_from_config
        spec = verifier_spec_from_config({"mode": "shared", "command": "echo hello"})
        assert spec.command == ["echo hello"]
