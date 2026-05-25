# Migrating Benchmark Adapters to Sample

This guide covers migrating benchmark adapters from returning raw `dict` samples to the structured `Sample` model.

## Why Migrate?

The `Sample` dataclass provides:
- **Typed fields**: `id`, `input`, `target`, `choices`, `metadata`, `files`, `sandbox_override`
- **Backward compatibility**: `Sample.to_dict()` and `dict(sample)` produce legacy dicts
- **MCQ support**: `choices` + `target` fields for multiple-choice benchmarks
- **Better tooling**: IDE completion, type checking, conformance validation

## Migration Steps

### 1. Import Sample

```python
from snowl.core.sample import Sample
```

### 2. Update _row_to_sample return type

```python
# Before
def _row_to_sample(self, row, *, row_index, row_split, selected_count) -> dict[str, Any] | None:

# After
def _row_to_sample(self, row, *, row_index, row_split, selected_count) -> Sample | dict[str, Any] | None:
```

### 3. Return Sample instead of dict

```python
# Before
return {
    "id": task_id,
    "input": prompt,
    "metadata": {"category": category},
}

# After
return Sample(
    id=task_id,
    input=prompt,
    metadata={"category": category},
)
```

### 4. MCQ benchmarks: use choices + target

```python
# Before
return {
    "id": q_id,
    "input": question,
    "metadata": {"choices": ["A", "B", "C", "D"], "answer": "B"},
}

# After
return Sample(
    id=q_id,
    input=question,
    choices=["A", "B", "C", "D"],
    target="B",
    metadata={"subject": subject},
)
```

### 5. No need to call to_dict()

`BaseBenchmarkAdapter.load_tasks()` auto-converts dict samples to `Sample` instances. If your adapter returns `Sample`, it passes through directly. **Do not call `sample.to_dict()` at the end of `_row_to_sample()`**.

## Backward Compatibility

- `Sample` supports `dict(sample)` and `sample["key"]` for legacy code
- `Sample.to_dict()` produces the legacy dict format
- `Sample.from_dict()` converts legacy dicts to `Sample`
- `Task.iter_typed_samples()` handles both `dict` and `Sample` inputs
- `Task.iter_samples()` also handles both (returns raw objects as-is)

## Verification

After migration, run the conformance check:

```bash
snowl bench check <benchmark_name>
```

And verify in tests:

```python
from snowl.core.sample import Sample

def test_adapter_returns_sample():
    adapter = MyBenchmarkAdapter()
    sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
    assert isinstance(sample, Sample)
```

## Migrated Adapters

These adapters already return `Sample` instances:
- `cybench` — `CyBenchBenchmarkAdapter`
- `humaneval` — `HumanEvalBenchmarkAdapter`
- `swe_bench` — `SWEBenchBenchmarkAdapter`
- `math_bench` — `MATHBenchmarkAdapter`
- `webarena` — `WebArenaBenchmarkAdapter`
