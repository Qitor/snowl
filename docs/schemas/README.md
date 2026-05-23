# Benchmark Manifest Schemas

## snowl.benchmark_manifest.v1

The benchmark manifest is a YAML or JSON document describing a benchmark adapter's metadata, source attribution, runtime requirements, and scoring method.

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Must be `"snowl.benchmark_manifest.v1"` |
| `name` | string | Machine-readable name (snake_case) |
| `display_name` | string | Human-readable name |
| `benchmark_type` | enum | One of: `capability`, `safety`, `tool_use`, `knowledge`, `reasoning`, `other` |
| `primary_metric` | string | Name of the primary scoring metric |
| `source` | object | Source attribution (paper, code, dataset, license) |
| `adapter` | object | Adapter entry point and min snowl version |
| `runtime` | object | Runtime requirements (docker, network, browser, GUI) |
| `scoring` | object | Scoring method documentation |

### Example

```yaml
schema_version: snowl.benchmark_manifest.v1
name: agentdojo
display_name: AgentDojo
family: agentdojo
domain: agentic_safety
benchmark_type: tool_use
primary_metric: agentdojo_score
higher_is_better: true
status: stable

source:
  paper: "https://arxiv.org/abs/2406.11420"
  code: "https://github.com/ethz-spylab/agentdojo"
  dataset: null
  homepage: null
  citation: null
  license: MIT

adapter:
  entrypoint: snowl_evals.agentdojo:adapter
  min_snowl_version: "0.1.0"

runtime:
  env_type: local
  requires_network: false
  requires_docker: false
  requires_browser: false
  requires_gui: false
  expected_minutes_per_100_samples: 30
  api_call_amplification: 5.0

data:
  included: false
  download_required: true
  local_path_env: null
  checksum: null

scoring:
  method: composite_utility_security
  judge_model_required: false
  notes: "50/50 utility + security scoring"

reproducibility:
  deterministic: false
  seed_supported: true
  known_caveats: []

maintainers:
  - name: Qitor
    contact: null
```

### Validation

Use the Python API:

```python
from snowl.benchmarks.manifest import validate_manifest, load_manifest

# From a YAML file
manifest = load_manifest("benchmark.yaml")

# From a dict
validate_manifest({"schema_version": "snowl.benchmark_manifest.v1", ...})
```

Or the JSON Schema directly at `docs/schemas/benchmark_manifest_v1.schema.json`.
