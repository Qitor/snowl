# Package 6: Frontend Split — Risk Dashboard vs Runs

## Goal

Separate the public product homepage from the operator run monitor.

## Directly affected files

- `webui/src/components/dashboard.tsx`
- `webui/src/app/page.tsx`
- `webui/src/app/runs/page.tsx` (new)
- `webui/src/components/risk-monitor-page.tsx` (new)
- `webui/src/components/domain-overview-panel.tsx` (new)
- `webui/src/components/leaderboard-table.tsx` (new)
- `webui/src/components/benchmark-detail-panel.tsx` (new)
- `webui/src/components/benchmark-sample-drawer.tsx` (new)
- `webui/src/components/run-gallery-page.tsx`
- `webui/src/components/compare-page.tsx`
- `webui/src/lib/types.ts`

## Why this is necessary

Right now the homepage behaves like an operator monitor because `dashboard.tsx` effectively re-exports the run gallery.

That is useful internally, but the AIRiskMonitor-style product layer needs a different top-level information architecture.

## Required UI information architecture

### `/`
Render `RiskMonitorPage`

Homepage sections:
- domain cards
- capability/safety leaderboard toggle
- risk index ranking
- benchmark family navigator
- latest benchmarked runs (secondary)

### `/runs`
Render the existing run gallery operator experience

### `/compare`
Keep the compare experience, but add groupings:
- by benchmark family
- by domain

## Required component behaviors

### `run-gallery-page.tsx`
Keep the current run-centric view, but add filter facets:
- domain
- benchmark type
- company
- source type
- reasoning

### `benchmark-detail-panel.tsx`
Show:
- benchmark metadata
- primary metric
- leaderboard rows
- sample previews
- deep links to related runs

### `benchmark-sample-drawer.tsx`
Render benchmark-specific sample cards based on `sample_preview_mode`.

## Acceptance criteria

- `/` becomes a risk dashboard
- `/runs` preserves operator workflows
- benchmark cards can deep-link into run detail or compare views
- compare view can aggregate by domain/family

## Do not do in this package

- do not overload the homepage with raw run cards
- do not break the current run workspace
