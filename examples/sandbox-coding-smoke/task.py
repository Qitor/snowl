from snowl.core import EnvSpec, Task


def _samples():
    yield {
        "id": "fix-add",
        "input": "Fix src/app.py so add(1, 2) returns 3.",
        "metadata": {
            "workspace": {
                "enabled": True,
                "repo_files": {
                    "src/app.py": "def add(a, b):\n    return 0\n",
                    "tests/test_app.py": "from src.app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                },
            },
            "required_changed_paths": ["src/app.py"],
            "check_command": "python -m pytest -q",
        },
    }


task = Task(
    task_id="sandbox-coding-smoke",
    env_spec=EnvSpec(env_type="terminal", provided_ops=("process.run", "terminal.exec", "terminal.capture", "terminal.wait")),
    sample_iter_factory=_samples,
    metadata={
        "benchmark": "sandbox_coding_smoke",
        "primary_metric": "workspace_changed",
    },
)

