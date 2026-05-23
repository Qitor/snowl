# External Packages

The former `snowl-evals-prototype` has been extracted into the standalone `snowl-evals` package.

During local development, place it as a sibling directory:

```
snowl/
snowl-evals/
```

Then run:

```bash
pip install -e ./snowl
pip install -e ./snowl-evals
snowl bench doctor
```

For the cross-repository integration check:

```bash
scripts/check_snowl_evals_integration.sh
```
