# Release Process

Snowl publishes to PyPI through GitHub Trusted Publishing. The PyPI publisher
must match:

- project name: `snowl`
- repository: `Qitor/snowl`
- workflow: `pypi-publish.yml`
- environment: any

## Prepare A Release

1. Update `pyproject.toml` and `snowl/__init__.py` to the same version.
2. Run the focused package checks:

   ```bash
   python -m build --outdir /tmp/snowl-package-check
   python -m twine check /tmp/snowl-package-check/*
   python scripts/package_smoke.py --dist-dir /tmp/snowl-package-check
   ```

3. Run the normal test suite:

   ```bash
   pytest -q
   ```

4. Confirm the package artifacts do not contain local runtime or dependency
   caches such as `node_modules`, `.snowl`, `.next/cache`, `*.tsbuildinfo`, or
   `__pycache__`.

## Publish

Publishing does not use a PyPI API token. The release workflow requests an OIDC
identity token from GitHub Actions and PyPI verifies the trusted publisher.

Preferred path:

```bash
git tag v0.1.1
git push origin v0.1.1
gh release create v0.1.1 --title "Snowl v0.1.1" --notes "Release notes..."
```

Manual path for maintainers:

```bash
gh workflow run pypi-publish.yml --ref main
gh run watch <run-id> --exit-status
```

If publishing fails before upload, fix the workflow or package metadata and
rerun the workflow. If upload succeeds, do not reuse the same version; PyPI
versions are immutable, so bump the patch version before publishing again.

## Verify After Publish

```bash
python -m venv /tmp/snowl-release-check
/tmp/snowl-release-check/bin/python -m pip install --upgrade pip
/tmp/snowl-release-check/bin/python -m pip install snowl
/tmp/snowl-release-check/bin/snowl --help
/tmp/snowl-release-check/bin/snowl bench list
/tmp/snowl-release-check/bin/snowl bench check strongreject
curl -L --fail https://pypi.org/pypi/snowl/json
```

The web monitor may need Node.js and npm when it first prepares the bundled
Next.js monitor. Plain CLI and benchmark checks should work without starting the
web monitor.

## Optional Sandbox Smoke

The real Docker sandbox smoke is intentionally manual so regular CI can run
without privileged Docker assumptions:

```bash
gh workflow run sandbox-smoke.yml --ref main
```

Locally:

```bash
snowl eval examples/sandbox-coding-smoke/project.yml --no-web-monitor
snowl eval examples/sandbox-coding-smoke/docker-project.yml --no-web-monitor
```
