.PHONY: up down build logs smoke-test test-backend clean

up:
	docker compose up -d
	@echo "API:       http://localhost:8000/docs"
	@echo "Dashboard: http://localhost:3000"

build:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker beat

logs-frontend:
	docker compose logs -f frontend

smoke-test:
	./smoke_test.sh

test-backend:
	cd backend && pip install -r requirements.txt && pytest tests/ -v

clean:
	docker compose down -v
	@echo "Stopped containers and removed the Postgres volume (all data wiped)."
