.PHONY : check1 mypy isort black ruff lint pytest

MODEL=./tests/models/simple.mps.bz2

check1:
	uv run bendee simple_milp $(MODEL)
	uv run bendee simple_milp -f iterative $(MODEL)
	uv run bendee simple_milp -r subgradient $(MODEL)
	uv run bendee simple_milp -f iterative -r subgradient --loglevel info $(MODEL)

mypy:
	uv run mypy --python-executable=.venv/bin/python --install-types --non-interactive src/bendee

isort:
	uvx ruff check --select I --fix

black:
	uvx ruff format

ruff:
	uvx ruff check

test:
	uv run pytest ./tests

lint: isort black ruff