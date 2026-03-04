# Snowl Panel Configs

Load precedence:

1. `default.yml`
2. `<benchmark>.yml` (e.g. `strongreject.yml`, `terminalbench.yml`, `osworld.yml`)
3. user override in project root: `panels.yml` / `panels.yaml`

Effective config is merged by `panel_type` key and layout columns.

Schema:

- `panels[]`
  - `type`: panel_type id
  - `title`: UI title
  - `source`: logical data source
  - `transform`: transform preset id
  - `visibility`: `always|when_env_present|when_model_io_present|when_scorer_present`
- `layout`
  - `left`: ordered panel_type list
  - `right`: ordered panel_type list

Common panel_type examples:
- `overview`, `task_queue`, `task_detail`, `event_stream`
- `env_timeline`, `action_stream`, `observation_stream`
- `model_io`, `scorer_explain`, `compare_board`, `failures`
