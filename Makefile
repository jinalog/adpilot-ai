.PHONY: install run-api run-ui test lint format migrate compose-up compose-down

install:
	python -m pip install -e ".[dev,frontend]"

run-api:
	uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000

run-ui:
	streamlit run frontend/app.py --server.port 8501

test:
	pytest

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

migrate:
	alembic upgrade head

compose-up:
	docker compose up -d postgres
	docker compose run --rm --build backend alembic upgrade head
	docker compose up --build

compose-down:
	docker compose down
