# Snowl Live CLI Demo (P1)

This demo is designed for showcase runs with a single command.

## One-command demo

```bash
snowl eval examples/terminalbench-official --keys "p,p,task=terminalbench:test,agent=terminalbench_official_agent,variant=default,m,f,r" 
```

What this demonstrates in one run:

- pause/resume (`p`)
- in-session filters (`task=...`, `agent=...`, `variant=...`)
- compare sort toggle (`m` metric sort)
- failed-only focus (`f`)
- rerun-failed request (`r`)
- live container startup/config events in event stream

## Equivalent scripted run (no UI)

```bash
snowl eval examples/terminalbench-official --no-ui --task terminalbench:test --agent terminalbench_official_agent --variant default --rerun-failed-only
```

The live run writes parity metadata to:

- `.snowl/runs/<run_id>/profiling.json` -> `interaction.equivalent_cli`
- `.snowl/runs/<run_id>/run.log`
