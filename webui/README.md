# Snowl Web UI

Next.js monitor for Snowl evaluation runs.

## Local run (standalone)

```bash
cd webui
npm install
npm run dev -- --hostname 127.0.0.1 --port 8765
```

Environment variables:

- `SNOWL_PROJECT_DIR`: project root containing `.snowl/runs`
- `SNOWL_POLL_INTERVAL_SEC`: run discovery / ingestion poll interval

The CLI wrapper is:

```bash
snowl web monitor --project . --host 127.0.0.1 --port 8765
```

`snowl web monitor` runs directly from this webui directory (no runtime cache copy). Install-time build happens during `pip install -e .` / `python setup.py install`.
