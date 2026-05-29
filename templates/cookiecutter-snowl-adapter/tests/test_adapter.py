"""Basic conformance test for the {{cookiecutter.adapter_name}} adapter."""

from {{cookiecutter.module_name}}.adapter import {{cookiecutter.class_name}}


def test_adapter_framework_name():
    adapter = {{cookiecutter.class_name}}()
    assert adapter.framework_name == "{{cookiecutter.framework_name}}"


def test_wrap_returns_agent_with_id():
    class FakeAgent:
        name = "test-agent"

    adapter = {{cookiecutter.class_name}}()
    wrapped = adapter.wrap(FakeAgent())
    assert hasattr(wrapped, "agent_id")
    assert "{{cookiecutter.framework_name}}" in wrapped.agent_id


def test_wrap_returns_agent_with_run():
    class FakeAgent:
        name = "test-agent"

    adapter = {{cookiecutter.class_name}}()
    wrapped = adapter.wrap(FakeAgent())
    assert hasattr(wrapped, "run")
    assert callable(wrapped.run)
