from snowl.core import EnvSpec, Task


task = Task(
    task_id="placeholder",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=lambda: iter([]),
)
