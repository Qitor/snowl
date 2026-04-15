# Container Lifecycle Management

This document describes the container ownership contract that exists today. It is about current runtime behavior, not future pooling or scheduler design.

## Ownership Rule

For runtime-managed benchmarks, Snowl owns the container lifecycle.

That means:

- task/sample metadata declares whether the trial needs a container
- runtime resolves that declaration into one normalized contract
- runtime creates or acquires the provider session
- runtime registers the resource with run/trial ownership
- runtime releases and tears down the resource
- agents only consume the injected session

For TerminalBench and OSWorld, agent-side container startup fallback is no longer allowed.

## Contract Source

Runtime decides container ownership from `runtime_container` metadata only.

Current contract resolution:

- task-level defaults live in `Task.metadata["runtime_container"]`
- sample-level overrides live in `sample["metadata"]["runtime_container"]`
- `snowl/runtime/container_contract.py` merges them into `RuntimeContainerSpec`

Key normalized fields:

- `benchmark`
- `provider_name`
- `requires_container`
- `cleanup_policy`
- `debug_preserve_default`
- `startup`
- `spec_hash_basis`
- derived `spec_hash`

Do not make agents inspect raw benchmark-specific metadata such as `docker_compose_path` or `osworld_settings` to decide ownership. Those fields may still exist for benchmark logic, but they are not the ownership contract.

## Runtime Files

- `snowl/runtime/container_contract.py`
  - resolves the task/sample contract
- `snowl/runtime/container_runtime.py`
  - bridges one trial into provider prepare/finalize and lifecycle registration
- `snowl/runtime/container_lifecycle.py`
  - owns registration, lease/release, teardown, preserve policy, and run cleanup
- `snowl/runtime/container_providers.py`
  - provider-specific start/stop implementations for TerminalBench and OSWorld
- `snowl/runtime/engine.py`
  - injects `__snowl_container_session` and `__snowl_runtime_container_spec`
- `snowl/eval.py`
  - creates one lifecycle manager per run and executes the run-end cleanup barrier

## Trial Lifecycle

Current lifecycle for a runtime-managed container:

1. `prepare_trial_phase()` creates `ContainerRuntime`.
2. `ContainerRuntime` resolves `RuntimeContainerSpec`.
3. Provider prepare returns a concrete session.
4. Runtime registers the resource immediately and leases it to the trial.
5. Agent consumes `__snowl_container_session`.
6. `finalize_trial_phase()` releases the lease.
7. Default policy destroys the resource on release.

Current lifecycle states in `snowl/runtime/container_lifecycle.py`:

- `CREATED`
- `LEASED`
- `IDLE_WARM`
- `DIRTY`
- `RECYCLING`
- `DESTROYED`
- `CLEANUP_FAILED`

`IDLE_WARM` exists in the model, but benchmark container warm reuse is not enabled by default today.

## Run-End Cleanup Barrier

Snowl now runs a cleanup barrier in the `run_eval()` mainline `finally` path.

Current behavior:

- normal completion triggers cleanup
- fatal failure triggers cleanup
- cancellation/interruption triggers best-effort cleanup
- cleanup runs before `events.jsonl` is closed so events are persisted

Current observability:

- `runtime.resource.registered`
- `runtime.resource.leased`
- `runtime.resource.released`
- `runtime.resource.teardown.start`
- `runtime.resource.teardown.finish`
- `runtime.resource.teardown.failed`
- `runtime.cleanup.barrier.start`
- `runtime.cleanup.barrier.finish`
- `runtime.cleanup.leak_suspected`

`profiling.json` now includes `container_cleanup`.

## Default Cleanup Policy

Current default:

- benchmark containers are destroyed on release
- run-end cleanup tears down surviving runtime-owned resources
- Snowl should not leave runtime-owned containers alive accidentally after a run

Explicit preserve modes:

- `snowl eval ... --keep-containers`
- `snowl eval ... --keep-failed-containers`
- the same flags are also available on `snowl retry` and `snowl bench run`

Preservation is explicit and visible in cleanup summary/event output. It is not the default.

## Current Benchmark Coverage

Standardized runtime-owned paths today:

- TerminalBench
- OSWorld

What is standardized for them:

- task-declared `runtime_container` contract
- runtime-managed session injection
- runtime-owned registration and cleanup
- agent contract violation if required session is missing

## Known Limits

- `max_container_slots` still does not universally gate every container prepare path.
- `spec_hash` is recorded but does not yet drive reuse or locality-aware dispatch.
- runtime does not pool or reuse benchmark containers by default.
- stale-resource janitor behavior for hard-crashed historical runs is not implemented yet.
- future container-backed benchmarks must explicitly adopt `runtime_container`; they do not get lifecycle ownership automatically.
