# Sandbox Coding Smoke

Minimal project showing Snowl runtime-owned workspaces for coding-agent style
benchmarks. The task seeds a tiny repository, the agent edits the isolated
workspace, and the scorer checks the resulting file diff.

```bash
snowl eval examples/sandbox-coding-smoke/project.yml
```

