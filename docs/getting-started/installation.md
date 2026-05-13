# Installation

## Requirements

- Python 3.10 or later
- pip or uv package manager

## Install from source

```bash
git clone https://github.com/Qitor/snowl.git
cd snowl
pip install -e .
```

## Optional dependencies

### Safety assets

For benchmarks that download datasets from Hugging Face or remote URLs:

```bash
pip install -e ".[safety_assets]"
```

This installs `datasets` and `huggingface_hub` for remote asset caching.

### OSWorld evaluation

For the OSWorld GUI desktop benchmark, which requires many additional packages:

```bash
pip install -e ".[osworld_eval]"
```

### Development

For running tests and contributing:

```bash
pip install -e ".[dev]"
```

This installs `pytest` and build/publish tools.

## Verify installation

```bash
snowl bench list
```

This prints all built-in benchmark adapters, confirming the installation works.

## Docker (optional)

Some benchmarks (TerminalBench, OSWorld) require Docker for container-backed
execution. Ensure Docker is running if you plan to evaluate these benchmarks:

```bash
docker info
```

## Next step

[Quick Start &rarr;](quick-start.md)
