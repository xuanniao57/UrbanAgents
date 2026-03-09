# Contributing to UrbanAgent

## Development setup

1. Create or activate a Python 3.10+ environment.
2. Install the package in editable mode: `pip install -e .[dev]`
3. For the broader benchmark stack, install additional packages from `requirements_combined.txt` as needed.

## Workflow

1. Add or update tests for every user-visible change.
2. Run `pytest` before submitting changes.
3. Update `README.md` or docs when behavior, setup, or public APIs change.

## Scope boundaries

- Keep core package changes focused and backward compatible where possible.
- Treat benchmark assets under `third_party/` as vendored dependencies unless the task explicitly requires modification.
- Do not commit secrets, API keys, or local machine paths.

## Pull request checklist

1. Tests added or updated.
2. Documentation updated.
3. No hard-coded local secrets or credentials.
4. Changes validated on at least one local workflow.