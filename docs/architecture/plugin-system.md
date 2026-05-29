# Plugin System

Snowl discovers extensions via Python `entry_points`. This enables third-party packages to add benchmarks, adapters, and container providers without modifying Snowl itself.

## Entry Point Groups

### Benchmarks (`snowl.benchmarks`)

Register a benchmark adapter so `snowl bench run <name>` works:

```toml
# In your package's pyproject.toml
[project.entry-points."snowl.benchmarks"]
my_benchmark = "my_package.adapter:MyBenchmarkAdapter"
```

The adapter class must be a `BaseBenchmarkAdapter` subclass or provide a callable factory that returns one.

### Adapters (`snowl.adapters`)

Register a framework adapter so agents from your framework can run in Snowl evaluations:

```toml
[project.entry-points."snowl.adapters"]
my_framework = "my_package.adapter:MyFrameworkAdapter"
```

The adapter class must be a `BaseFrameworkAdapter` subclass.

### Container Providers (`snowl.container_providers`)

Register a container provider for benchmarks that need specialized container management:

```toml
[project.entry-points."snowl.container_providers"]
my_provider = "my_package.provider:MyContainerProvider"
```

The provider must implement the `ContainerProvider` protocol with `register_providers(registry)` method.

## Discovery Process

1. Snowl's registry calls `importlib.metadata.entry_points()` for each group
2. Each entry point is loaded lazily — the package is only imported when the benchmark/adapter/provider is actually needed
3. The loaded class is registered in the default registry

## Creating a Plugin Package

Use the cookiecutter template to generate a complete adapter package:

```bash
pip install cookiecutter
cookiecutter templates/cookiecutter-snowl-adapter/
```

Or manually:

1. Create a Python package with your adapter/benchmark/provider
2. Declare the entry point in `pyproject.toml`
3. `pip install` your package alongside Snowl
4. Snowl auto-discovers it at runtime

## Namespace Package for Community Adapters

Third-party adapters can use the `snowl.adapters.contrib` namespace:

```toml
[project.entry-points."snowl.adapters"]
my_framework = "snowl.adapters.contrib.my_framework:MyFrameworkAdapter"
```

This keeps community adapters organized under a shared namespace without conflicts.
