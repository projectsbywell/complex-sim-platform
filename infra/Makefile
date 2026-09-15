setup:; pip install -r simulation-core/requirements.txt backend/requirements.txt; pip install -r tests/requirements-test.txt
test:; python -m pytest -q
load:; python tests/test_load.py
run-api:; uvicorn backend.app.main:app --reload --port 8000 --directory backend 2>/dev/null || (cd backend && uvicorn app.main:app --reload --port 8000)
run-ui:; python -m http.server 5173 --directory frontend
docker:; docker compose -f infra/docker-compose.yml up --build
clean:; find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true
