"""Tests for Sample dataclass, from_dict/to_dict, and Task.iter_typed_samples."""

import pytest

from snowl.core.sample import Sample
from snowl.core.task import Task
from snowl.core import EnvSpec


# ---------------------------------------------------------------------------
# Sample model
# ---------------------------------------------------------------------------

class TestSample:
    def test_create_minimal(self):
        s = Sample(id="s1", input="hello")
        assert s.id == "s1"
        assert s.input == "hello"
        assert s.target is None
        assert s.choices is None
        assert s.metadata == {}
        assert s.files is None
        assert s.sandbox_override is None

    def test_create_full(self):
        s = Sample(
            id="s2",
            input="q?",
            target="a",
            choices=["a", "b", "c"],
            metadata={"level": 1},
            files={"f.txt": "content"},
            sandbox_override={"docker": "python:3.12"},
        )
        assert s.target == "a"
        assert s.choices == ["a", "b", "c"]
        assert s.metadata["level"] == 1
        assert s.files["f.txt"] == "content"
        assert s.sandbox_override["docker"] == "python:3.12"

    def test_frozen(self):
        s = Sample(id="s1", input="hello")
        with pytest.raises(AttributeError):
            s.id = "changed"

    def test_input_multimodal(self):
        """input can be a list of content blocks (multimodal)."""
        content = [{"type": "text", "text": "describe"}, {"type": "image_url", "url": "http://x.png"}]
        s = Sample(id="s1", input=content)
        assert isinstance(s.input, list)
        assert len(s.input) == 2


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trip
# ---------------------------------------------------------------------------

class TestSampleSerialization:
    def test_roundtrip_minimal(self):
        s = Sample(id="s1", input="hello")
        d = s.to_dict()
        s2 = Sample.from_dict(d)
        assert s2 == s

    def test_roundtrip_full(self):
        s = Sample(
            id="s2",
            input="q?",
            target="a",
            choices=["a", "b"],
            metadata={"key": "val"},
            files={"f.txt": "c"},
            sandbox_override={"docker": "img"},
        )
        d = s.to_dict()
        s2 = Sample.from_dict(d)
        assert s2 == s

    def test_from_dict_extra_keys_ignored(self):
        """Extra keys in dict should not crash from_dict."""
        d = {"id": "s1", "input": "hi", "unknown_field": 42}
        s = Sample.from_dict(d)
        assert s.id == "s1"

    def test_to_dict_drops_defaults(self):
        """to_dict should only include non-None optional fields."""
        s = Sample(id="s1", input="hello")
        d = s.to_dict()
        assert "choices" not in d
        assert "files" not in d
        assert "sandbox_override" not in d


# ---------------------------------------------------------------------------
# Task.iter_typed_samples
# ---------------------------------------------------------------------------

class TestTaskIterTypedSamples:
    def test_iterates_dicts(self):
        raw_samples = [{"input": "q1"}, {"input": "q2"}]

        def factory():
            return iter(raw_samples)

        task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=factory)
        typed = list(task.iter_typed_samples())
        assert len(typed) == 2
        assert all(isinstance(s, Sample) for s in typed)
        assert typed[0].input == "q1"

    def test_iterates_sample_instances(self):
        samples = [Sample(id="a", input="q1"), Sample(id="b", input="q2")]

        def factory():
            return iter(samples)

        task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=factory)
        typed = list(task.iter_typed_samples())
        assert len(typed) == 2
        assert typed[0].id == "a"

    def test_iterates_mixed(self):
        mixed = [Sample(id="a", input="q1"), {"input": "q2", "id": "b"}]

        def factory():
            return iter(mixed)

        task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=factory)
        typed = list(task.iter_typed_samples())
        assert len(typed) == 2
        assert isinstance(typed[0], Sample)
        assert isinstance(typed[1], Sample)

    def test_rejects_bad_type(self):
        bad = [42]

        def factory():
            return iter(bad)

        task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=factory)
        with pytest.raises(TypeError, match="Expected Sample or dict"):
            list(task.iter_typed_samples())
