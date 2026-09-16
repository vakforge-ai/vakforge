.PHONY: sync test lint fmt

sync:
	uv sync --group dev

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

fmt:
	uv run ruff check --fix . && uv run ruff format .
