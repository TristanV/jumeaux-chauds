.PHONY: install install-all dev test test-cov test-phase7 test-yaml test-telemetry test-commands test-energy docker-up docker-down docker-storage lint format

install:
	pip install -r requirements.txt

install-all:
	pip install -r requirements.txt -r requirements.dashboard.txt -r requirements.test.txt

dev:
	MQTT_BROKER_HOST=localhost uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Tests
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=simulation --cov=config --cov-report=html --cov-report=term-missing

test-phase7:
	@echo "=== Running Phase 7.1 Tests (Machine YAML Integration, Telemetry, Commands, Energy) ==="
	pytest tests/test_machine_yaml_integration.py tests/test_machine_telemetry.py tests/test_machine_commands.py tests/test_energy_conformity.py -v \
		--cov=simulation --cov=config \
		--cov-report=term-missing --cov-report=html
	@echo "✅ Phase 7.1 tests complete. Coverage report: htmlcov/index.html"

test-yaml:
	pytest tests/test_machine_yaml_integration.py -v

test-telemetry:
	pytest tests/test_machine_telemetry.py -v

test-commands:
	pytest tests/test_machine_commands.py -v

test-energy:
	pytest tests/test_energy_conformity.py -v

# Docker
docker-up:
	docker compose up

docker-down:
	docker compose down

docker-storage:
	docker compose --profile storage up

# Linting & formatting
lint:
	ruff check .

format:
	ruff format .
