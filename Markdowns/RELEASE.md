# Release 0.1.0 preparation

Prepared on 2026-09-17. Version 0.1.0 retained by request. This is a local
release candidate; no package upload, release tag, or deployment was performed.

## Changes

- Preserve worksheet function name spelling, underscores, and periods in IDs
  and metadata; retain case-insensitive duplicate checks and kernel lookup.

- Support `JUPYTEREXCEL_NAMESPACE` for the formula namespace, defaulting to
  `Jupyter`, with validation and preservation of published assets on failure.

- Preserve the README revisions and documentation under `Markdowns/`; add a
  documentation index and root instructions pointer.
- Correct README asset-hosting and Jupyter Server configuration examples.
- Restore the missing root `LICENSE-MIT` from its unchanged packaged notice.
- Include documentation, tests, examples, and server configuration in the source
  distribution, alongside the frontend source and prebuilt extension.
- Keep action results available after cancelling an overwrite, allowing retry.
- Isolate API URL tests from machine-specific environment settings.

## Validation

- Python 3.12: 78 unittest checks passed, including real kernel integration.
- Node: 25 client checks and 2 frontend workflow checks passed.
- TypeScript compilation and Python module compilation passed.
- Source archive and wheel built with `python -m build --no-isolation`.
- Both artifacts passed `python -m twine check --strict dist/*`.
- Existing prebuilt JupyterLab assets retained; frontend source was unchanged.

## Before publication

- Live Excel-to-Jupyter verification has not been performed in this preparation.
  Verify authentication, worksheet calculation, save/reload, range selection,
  formatted output, and overwrite cancellation/retry in Excel.
- `npm audit --omit=dev` reports 16 moderate dependency-tree findings, with no
  high or critical findings. Review these before publication. No forced major
  dependency changes were applied as part of release preparation.
- Record the actual first public BSL distribution date and its fourth anniversary
  when publishing. This preparation date is not a public distribution date.
- Confirm 0.1.0 is available in the intended package index and is distinct from
  prior MIT releases before uploading; this preparation did not query the index.

## Reproduce

From the repository root, using Python with the project dependencies installed:

```powershell
python -m pip install -e ".[test]" build twine
python -m unittest discover -s tests -v
node --test tests/*.cjs
npm --prefix frontend ci
npm --prefix frontend test
python -m build
python -m twine check --strict dist/*
git diff --check
```
