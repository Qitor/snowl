# Sandbox Coding Smoke

Minimal project showing Snowl runtime-owned workspaces for coding-agent style
benchmarks. The task seeds a tiny repository, the agent edits the isolated
workspace, and the scorer checks the resulting file diff.

Run the local workspace-only smoke:

```bash
snowl eval examples/sandbox-coding-smoke/project.yml --no-web-monitor
```

Run the Docker-backed smoke when Docker is available:

```bash
snowl eval examples/sandbox-coding-smoke/docker-project.yml --no-web-monitor
```

The Docker variant uses the generic `docker_container` provider, mounts the
runtime-owned workspace at `/workspace`, disables container networking, runs an
init command, verifies the patched file with a check command, and then tears the
container down during finalize.
