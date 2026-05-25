"""Environment provider template — copy and customize for your infrastructure.

Steps:
1. Copy this file to snowl/envs/<provider_name>.py
2. Implement the EnvironmentProvider ABC methods
3. Register in pyproject.toml [project.entry-points."snowl.environment_providers"]
4. Test with: project.yml runtime.environment_provider: <provider_name>

Replace all placeholder values marked with {{...}}.
"""

from __future__ import annotations

from typing import Any

from snowl.envs.provider import EnvironmentProvider, EnvironmentHandle


class {{ProviderName}}Provider(EnvironmentProvider):
    """Custom environment provider for {{provider_name}} infrastructure.

    Implement the EnvironmentProvider ABC to integrate your sandbox/container
    platform with Snowl's evaluation runtime.
    """

    provider_name: str = "{{provider_name}}"

    async def create(self, spec: Any, **kwargs: Any) -> EnvironmentHandle:
        """Create a new environment instance from the given spec.

        Args:
            spec: EnvSpec describing the required environment.
            **kwargs: Additional provider-specific configuration.

        Returns:
            An EnvironmentHandle for the created environment.
        """
        # TODO: Implement environment creation
        raise NotImplementedError

    async def destroy(self, handle: EnvironmentHandle) -> None:
        """Tear down and clean up an environment instance.

        Args:
            handle: The environment handle to destroy.
        """
        # TODO: Implement environment teardown
        raise NotImplementedError

    async def execute(
        self,
        handle: EnvironmentHandle,
        command: str,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a command inside the environment.

        Args:
            handle: The environment handle.
            command: Shell command to execute.
            env: Optional environment variables.
            timeout: Optional timeout in seconds.

        Returns:
            Dict with 'exit_code', 'stdout', 'stderr' keys.
        """
        # TODO: Implement command execution
        raise NotImplementedError

    async def healthcheck(self, handle: EnvironmentHandle) -> bool:
        """Check if an environment is healthy and responsive.

        Args:
            handle: The environment handle.

        Returns:
            True if the environment is healthy, False otherwise.
        """
        # TODO: Implement health check
        return True

    @property
    def max_concurrency(self) -> int:
        """Maximum number of concurrent environments this provider supports."""
        # TODO: Return actual concurrency limit
        return 10
