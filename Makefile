# Makefile — `make dev` on systems that have GNU make (macOS/Linux, or Windows
# with make installed). On stock Windows without make, use ./dev.ps1 instead.

.PHONY: dev backend frontend setup test

dev:
	@echo "Starting backend (:8010) and frontend (:5173)..."
	@$(MAKE) -j2 backend frontend

backend:
	cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload --reload-dir app

frontend:
	cd frontend && npm run dev

setup:
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

test:
	cd backend && python -m pytest
