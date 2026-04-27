# Package 3: Model Metadata and Dashboard Filters

## Goal

Add model/variant metadata needed for AIRiskMonitor-style filtering without prematurely forcing a multi-provider redesign.

## Directly affected files

- `snowl/project_config.py`
- `snowl/eval.py`
- `webui/src/lib/types.ts`
- `tests/test_project_model_matrix.py`
- `tests/test_project_model_metadata.py` (new)

## Why this package exists

The current project config is sufficient for running models, but not for organizing results into faceted views such as:
- company
- country
- source type
- reasoning
- model family

For this iteration, the lowest-friction approach is to attach this metadata to `agent_matrix.models[*]`.

## Required code changes

### 1. Extend config schema in `snowl/project_config.py`

Support:

```yaml
agent_matrix:
  models:
    - id: gpt5-high
      model: openai/gpt-5.2-high
      metadata:
        company: OpenAI
        country: US
        source_type: closed_source
        license_type: proprietary
        reasoning: high
        model_family: GPT-5
        release_channel: stable
```

### 2. Validate and normalize metadata

Add validation rules:
- `source_type` in `{"open_source", "closed_source"}`
- `reasoning` in `{"none", "low", "medium", "high", "unknown"}`
- `company`, `country`, `model_family` should be normalized strings

### 3. Propagate metadata in `snowl/eval.py`

Make model metadata available in:
- variant payload
- manifest
- outcomes
- aggregate rows

### 4. Update frontend types in `webui/src/lib/types.ts`

Extend types used by:
- run gallery
- compare page
- risk dashboard

Fields to add:
- `domain`
- `benchmark_type`
- `company`
- `country`
- `source_type`
- `license_type`
- `reasoning`
- `model_family`
- `capability_score`
- `safety_score`
- `risk_index`

## Acceptance criteria

- a model entry can carry metadata in project config
- metadata appears in run and aggregate APIs
- frontend can filter on company/source type/reasoning without hardcoding

## Do not do in this package

- do not redesign provider abstraction
- do not move all metadata into a separate registry service
