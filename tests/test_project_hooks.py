"""Tests for project.yml hooks declaration support."""

import pytest

from snowl.project_config import _parse_hooks, _VALID_HOOK_NAMES
from snowl.errors import SnowlValidationError
from pathlib import Path


_DUMMY_PATH = Path("/dummy/project.yml")


class TestParseHooks:
    def test_none_returns_none(self):
        assert _parse_hooks(None, path=_DUMMY_PATH) is None

    def test_empty_list_returns_none(self):
        # Empty list returns empty list (not None) — caller decides
        result = _parse_hooks([], path=_DUMMY_PATH)
        assert result == []

    def test_single_hook(self):
        data = [{"name": "cost_tracker"}]
        result = _parse_hooks(data, path=_DUMMY_PATH)
        assert len(result) == 1
        assert result[0]["name"] == "cost_tracker"

    def test_hook_with_config(self):
        data = [{"name": "rate_limit_alert", "warn_after": 5, "window_seconds": 120}]
        result = _parse_hooks(data, path=_DUMMY_PATH)
        assert len(result) == 1
        assert result[0]["warn_after"] == 5
        assert result[0]["window_seconds"] == 120

    def test_multiple_hooks(self):
        data = [
            {"name": "cost_tracker"},
            {"name": "audit_log"},
            {"name": "progress"},
        ]
        result = _parse_hooks(data, path=_DUMMY_PATH)
        assert len(result) == 3

    def test_all_valid_hook_names(self):
        for name in _VALID_HOOK_NAMES:
            result = _parse_hooks([{"name": name}], path=_DUMMY_PATH)
            assert result[0]["name"] == name

    def test_not_list_rejected(self):
        with pytest.raises(SnowlValidationError, match="list"):
            _parse_hooks("cost_tracker", path=_DUMMY_PATH)

    def test_entry_not_mapping_rejected(self):
        with pytest.raises(SnowlValidationError, match="mapping"):
            _parse_hooks(["cost_tracker"], path=_DUMMY_PATH)

    def test_missing_name_rejected(self):
        with pytest.raises(SnowlValidationError, match="name"):
            _parse_hooks([{}], path=_DUMMY_PATH)

    def test_empty_name_rejected(self):
        with pytest.raises(SnowlValidationError, match="name"):
            _parse_hooks([{"name": ""}], path=_DUMMY_PATH)

    def test_invalid_hook_name_rejected(self):
        with pytest.raises(SnowlValidationError, match="name"):
            _parse_hooks([{"name": "custom_hook"}], path=_DUMMY_PATH)


class TestProjectEvalConfigHooksField:
    def test_hooks_field_exists(self):
        from snowl.project_config import ProjectEvalConfig
        config = ProjectEvalConfig(
            benchmark="test",
            code=None,
        )
        assert config.hooks is None

    def test_hooks_field_set(self):
        from snowl.project_config import ProjectEvalConfig
        hooks = [{"name": "cost_tracker"}, {"name": "rate_limit_alert", "warn_after": 5}]
        config = ProjectEvalConfig(
            benchmark="test",
            code=None,
            hooks=hooks,
        )
        assert config.hooks is not None
        assert len(config.hooks) == 2
