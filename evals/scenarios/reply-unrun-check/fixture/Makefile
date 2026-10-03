PYTHON ?= python3
COMPOSE = docker compose -f compose.integration.yml

.PHONY: test integration

# Unit tests: offline, against a fake transport.
test:
	$(PYTHON) -m unittest discover -s tests/unit -t . -q

# Integration tests: against the booking simulator, started in Docker and stopped afterwards.
integration:
	$(COMPOSE) up -d --wait
	BERTHBOOK_SIM_URL=http://127.0.0.1:8089 $(PYTHON) -m unittest discover -s tests/integration -t . -q; \
	status=$$?; $(COMPOSE) down; exit $$status
