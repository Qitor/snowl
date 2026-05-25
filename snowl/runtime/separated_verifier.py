"""Separated verifier executor for isolated scoring environments.

Framework role:
- Manages the lifecycle of a verifier container that runs scoring in isolation
  from the agent environment.
- Transfers workspace artifacts from agent to verifier via ``docker cp``.
- Executes verification commands and captures structured results.

Runtime/usage wiring:
- Used by ``score_trial_phase`` in engine.py when ``VerifierMode.SEPARATE`` is set.
- Consumes ``VerifierSpec`` from core (pure data) and ``ContainerBackend`` from substrate.

Change guardrails:
- Must not import from ``snowl.core`` except for ``VerifierSpec``/``VerifierMode``.
- Docker interactions are via ``ContainerBackend`` (no direct subprocess calls).
- Falls back gracefully when Docker is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from snowl.core.env import VerifierMode, VerifierSpec
from snowl.errors import SnowlValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifierResult:
    """Structured result from a verifier container execution."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    container_id: str
    artifacts_snapshot: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class SeparatedVerifierExecutor:
    """Manages a verifier container for isolated scoring.

    Lifecycle::

        executor = SeparatedVerifierExecutor(spec=verifier_spec, ...)
        try:
            await executor.prepare()
            await executor.transfer_artifacts(workspace_dir="/path/to/workspace")
            result = await executor.run_command("python check.py")
        finally:
            await executor.teardown()

    Or use the convenience ``execute()`` for a full lifecycle in one call.
    """

    def __init__(
        self,
        *,
        spec: VerifierSpec,
        run_id: str | None = None,
        trial_id: str | None = None,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if spec.mode != VerifierMode.SEPARATE:
            raise SnowlValidationError(
                "SeparatedVerifierExecutor requires VerifierMode.SEPARATE."
            )
        self._spec = spec
        self._run_id = run_id
        self._trial_id = trial_id
        self._emit = emit
        self._container_id: str | None = None
        self._backend: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def prepare(self) -> None:
        """Create and start the verifier container.

        Uses ``ContainerBackend.run()`` with the verifier image and
        ``sleep infinity`` so the container stays alive for commands.
        """
        from snowl.envs.substrate.container_backend import ContainerBackend
        from snowl.envs.substrate.command_runner import CommandRunner

        runner = CommandRunner()
        self._backend = ContainerBackend(command_runner=runner)

        image = self._spec.image
        if not image:
            raise SnowlValidationError(
                "VerifierSpec.image is required for SEPARATE mode."
            )

        name = f"snowl-verifier-{self._run_id or 'x'}-{self._trial_id or 'x'}"

        try:
            result = await asyncio.to_thread(
                self._backend.run,
                image=image,
                name=name,
                command="sleep infinity",
                detach=True,
                env=self._spec.environment or None,
                network=self._spec.network.get("mode") if self._spec.network else None,
            )
            container_id = result.get("container_id") or result.get("output", "").strip()
            if not container_id:
                # Fallback: try parsing from docker output
                output = str(result.get("output", "")).strip()
                container_id = output.split("\n")[0].strip() if output else ""
            self._container_id = container_id

            self._emit_event({
                "event": "runtime.verifier.prepare",
                "phase": "score",
                "container_id": self._container_id,
                "image": image,
            })

            logger.info("Verifier container started: %s (image=%s)", self._container_id, image)

        except Exception as exc:
            self._emit_event({
                "event": "runtime.verifier.error",
                "phase": "score",
                "step": "prepare",
                "message": str(exc),
            })
            raise

    async def transfer_artifacts(
        self,
        workspace_dir: str | None = None,
        files: dict[str, str] | None = None,
    ) -> None:
        """Copy workspace artifacts into the verifier container.

        Args:
            workspace_dir: Host directory to copy into ``/workspace/`` in the container.
            files: Dict of ``{container_path: content}`` to write as individual files.
        """
        if self._container_id is None:
            raise RuntimeError("Verifier container not prepared. Call prepare() first.")

        try:
            if workspace_dir:
                await asyncio.to_thread(
                    self._backend.cp,
                    source=str(workspace_dir) + "/.",
                    container_id=self._container_id,
                    dest="/workspace",
                )

            if files:
                # Write individual files: create a temp dir, write files, cp it
                import tempfile
                from pathlib import Path

                with tempfile.TemporaryDirectory(prefix="snowl-verifier-") as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    for rel_path, content in files.items():
                        file_path = tmp_path / rel_path
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(content, encoding="utf-8")
                    await asyncio.to_thread(
                        self._backend.cp,
                        source=str(tmp_path) + "/.",
                        container_id=self._container_id,
                        dest="/workspace",
                    )

            self._emit_event({
                "event": "runtime.verifier.transfer",
                "phase": "score",
                "container_id": self._container_id,
                "workspace_dir": workspace_dir,
            })

        except Exception as exc:
            self._emit_event({
                "event": "runtime.verifier.error",
                "phase": "score",
                "step": "transfer",
                "message": str(exc),
            })
            raise

    async def run_command(
        self,
        command: str,
        *,
        workdir: str | None = None,
        timeout_seconds: float | None = None,
    ) -> VerifierResult:
        """Execute a command in the verifier container.

        Args:
            command: Shell command to execute.
            workdir: Working directory inside the container.
            timeout_seconds: Execution timeout (overrides VerifierSpec default).

        Returns:
            VerifierResult with exit_code, stdout, stderr, and metadata.
        """
        if self._container_id is None:
            raise RuntimeError("Verifier container not prepared. Call prepare() first.")

        effective_timeout = timeout_seconds or self._spec.timeout_seconds

        try:
            result = await asyncio.to_thread(
                self._backend.exec,
                container_id=self._container_id,
                command=command,
                workdir=workdir or "/workspace",
                timeout_seconds=effective_timeout,
            )

            exit_code = result.get("exit_code", -1)
            stdout = str(result.get("output", ""))
            stderr = str(result.get("stderr", ""))
            timed_out = result.get("timed_out", False)

            verifier_result = VerifierResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                container_id=self._container_id,
                metadata={"command": command, "workdir": workdir},
            )

            self._emit_event({
                "event": "runtime.verifier.execute",
                "phase": "score",
                "container_id": self._container_id,
                "exit_code": exit_code,
                "timed_out": timed_out,
            })

            return verifier_result

        except Exception as exc:
            self._emit_event({
                "event": "runtime.verifier.error",
                "phase": "score",
                "step": "execute",
                "message": str(exc),
            })
            return VerifierResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                timed_out=True,
                container_id=self._container_id or "",
                metadata={"command": command, "error": str(exc)},
            )

    async def teardown(self) -> dict[str, Any]:
        """Remove the verifier container."""
        if self._container_id is None or self._backend is None:
            return {}

        try:
            result = await asyncio.to_thread(
                self._backend.rm,
                container_id=self._container_id,
                force=True,
            )
            self._emit_event({
                "event": "runtime.verifier.teardown",
                "phase": "score",
                "container_id": self._container_id,
            })
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            logger.warning("Failed to teardown verifier container: %s", exc)
            return {"error": str(exc)}
        finally:
            self._container_id = None

    async def execute(
        self,
        command: str,
        *,
        workspace_dir: str | None = None,
        workspace_files: dict[str, str] | None = None,
        workdir: str | None = None,
    ) -> VerifierResult:
        """Full lifecycle: prepare → transfer → run → teardown.

        Convenience method for one-shot verifier execution.
        """
        try:
            await self.prepare()
            await self.transfer_artifacts(
                workspace_dir=workspace_dir,
                files=workspace_files,
            )
            return await self.run_command(command, workdir=workdir)
        finally:
            await self.teardown()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self._emit is not None:
            try:
                self._emit(event)
            except Exception:
                pass

    @property
    def container_id(self) -> str | None:
        return self._container_id

    @property
    def is_prepared(self) -> bool:
        return self._container_id is not None


def verifier_spec_from_config(config: dict[str, Any] | None) -> VerifierSpec | None:
    """Construct a VerifierSpec from a project.yml verifier section.

    Args:
        config: Dict from ``eval.verifier`` in project.yml, or None.

    Returns:
        A VerifierSpec instance, or None if config is None/empty.
    """
    if not config:
        return None

    mode_str = str(config.get("mode", "shared")).strip().lower()
    try:
        mode = VerifierMode(mode_str)
    except ValueError:
        raise SnowlValidationError(
            f"Invalid verifier mode '{mode_str}'. Must be 'shared' or 'separate'."
        )

    priority_scorers_raw = config.get("priority_scorers", [])
    if not isinstance(priority_scorers_raw, (list, tuple)):
        raise SnowlValidationError("verifier.priority_scorers must be a list.")

    command_raw = config.get("command", [])
    if isinstance(command_raw, str):
        command_raw = [command_raw]

    spec = VerifierSpec(
        mode=mode,
        image=config.get("image"),
        build_context=config.get("build_context"),
        dockerfile=config.get("dockerfile"),
        command=list(command_raw),
        environment=dict(config.get("environment", {})),
        resources=dict(config.get("resources", {})),
        network=dict(config.get("network", {})),
        priority_scorers=tuple(str(s) for s in priority_scorers_raw),
        timeout_seconds=float(config.get("timeout_seconds", 120.0)),
        metadata=dict(config.get("metadata", {})),
    )

    from snowl.core.env import validate_verifier_spec
    validate_verifier_spec(spec)
    return spec
