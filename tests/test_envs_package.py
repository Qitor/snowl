from __future__ import annotations

from snowl.core import EnvSpec
from snowl.envs import LocalEnv, LocalSandboxRuntime
from snowl.runtime.sandbox import LocalSandboxRuntime as CompatLocalSandboxRuntime


def test_local_env_constructs_with_env_spec() -> None:
    env = LocalEnv(EnvSpec(env_type="local", provided_ops=("FileOps",)))
    assert env.env_id == "local:local"
    assert env.provided_ops == ("FileOps",)
    assert env.reset()["status"] == "reset"
    env.close()


def test_runtime_sandbox_module_keeps_compat_reexport() -> None:
    assert CompatLocalSandboxRuntime is LocalSandboxRuntime
