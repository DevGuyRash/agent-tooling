# Python Commands

Use this file when the repo uses Python.

## Detection order

1. uv
   - `uv.lock`
   - `[tool.uv]`
2. poetry
   - `poetry.lock`
   - `[tool.poetry]`
3. generic pip project
   - `pyproject.toml`
   - `setup.py`
   - `requirements.txt`

## Preferred command families

### uv

```text
build      uv build
test       uv run pytest
lint       uv run ruff check .
fmt        uv run ruff format .
fmt-check  uv run ruff format --check .
bootstrap  uv sync
```

### poetry

```text
build      poetry build
test       poetry run pytest
lint       poetry run ruff check .
fmt        poetry run ruff format .
fmt-check  poetry run ruff format --check .
bootstrap  poetry install
```

### pip project

Use a conservative fallback:

```text
build      python -m build
test       python -m pytest
lint       ruff check .
fmt        ruff format .
fmt-check  ruff format --check .
bootstrap  python -m pip install -e ".[dev]"
```

This assumes the repo is comfortable with standard Python developer tooling.
If the repo clearly uses another tool, wrap that instead.

## Framework signals

- Django: `manage.py` or `django`
- Flask: dependency inspection
- FastAPI: dependency inspection

Framework detection mainly informs bootstrap and developer expectations. It
should not force the justfile to become framework-specific unless the repo
already exposes framework-specific management commands.

## Virtual environment note

For a generalized harness, prefer command families that work without requiring
shell activation to persist across recipe lines. That is one reason uv and
poetry are good defaults when present.

## When to stop guessing

If the repo uses Hatch, PDM, tox, nox, or a bespoke wrapper and that tool is
clearly the project’s entry point, wrap that tool instead of imposing uv,
poetry, or pip conventions.
