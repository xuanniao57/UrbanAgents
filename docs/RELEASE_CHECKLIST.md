# UrbanAgent Release Checklist

## Minimum release gate

1. Update version in `urban_agent/version.py` and `pyproject.toml`.
2. Run `pytest` from the project root.
3. Validate one benchmark command and one web startup path.
4. Confirm `LICENSE`, `README.md`, and `CHANGELOG.md` are current.
5. Remove any local secrets from `.env` or logs.

## Recommended release assets

1. Tag the release in Git.
2. Publish benchmark artifacts used in the release note.
3. Summarize breaking changes and migration notes.
4. Link public issue tracker and documentation entrypoints.