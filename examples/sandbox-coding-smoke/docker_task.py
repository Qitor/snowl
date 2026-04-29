from snowl.core import EnvSpec, Task


def _samples():
    yield {
        "id": "fix-add-docker",
        "input": "Fix src/app.py so add(1, 2) returns 3. The runtime will verify the isolated workspace in Docker.",
        "metadata": {
            "workspace": {
                "enabled": True,
                "repo_files": {
                    "src/app.py": "def add(a, b):\n    return 0\n",
                    "tests/test_app.py": "from src.app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                },
            },
            "runtime_container": {
                "benchmark": "sandbox_coding_smoke",
                "provider_name": "docker_container",
                "requires_container": True,
                "network": "disabled",
                "init_command": "python --version",
                "check_command": "python -c \"from src.app import add; assert add(1, 2) == 3\"",
                "startup": {
                    "image": "python:3.12-slim",
                    "workspace_mount": "/workspace",
                    "command": "sleep infinity",
                    "workdir": "/workspace",
                },
                "resource_limits": {
                    "start_timeout_seconds": 180,
                    "init_timeout_seconds": 60,
                    "check_timeout_seconds": 60,
                    "stop_timeout_seconds": 60,
                },
            },
            "required_changed_paths": ["src/app.py"],
            "check_command": "python -c \"from src.app import add; assert add(1, 2) == 3\"",
        },
    }


task = Task(
    task_id="sandbox-coding-smoke-docker",
    env_spec=EnvSpec(env_type="terminal", provided_ops=("process.run", "terminal.exec", "terminal.capture", "terminal.wait")),
    sample_iter_factory=_samples,
    metadata={
        "benchmark": "sandbox_coding_smoke",
        "primary_metric": "workspace_changed",
    },
)
