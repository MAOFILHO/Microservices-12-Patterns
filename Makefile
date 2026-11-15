.PHONY: setup run provision pause resume teardown verify test smoke clean

setup:
	python3.12 scripts/setup.py

run:
	python3.12 scripts/run_local.py

provision:
	python3.12 infra/provision.py --budget-email "$(BUDGET_EMAIL)" $(ARGS)

pause:
	python3.12 infra/pause.py

resume:
	python3.12 infra/resume.py

teardown:
	python3.12 infra/teardown.py

verify:
	python3.12 infra/verify_teardown.py

test:
	.venv/bin/python -m pytest tests/unit -v
	services/user/.venv/bin/python -m pytest services/user/tests -v
	services/catalog/.venv/bin/python -m pytest services/catalog/tests -v
	services/order/.venv/bin/python -m pytest services/order/tests -v
	services/payment/.venv/bin/python -m pytest services/payment/tests -v
	services/inventory/.venv/bin/python -m pytest services/inventory/tests -v
	gateway/.venv/bin/python -m pytest gateway/tests -v

smoke:
	.venv/bin/python -m pytest tests/smoke -v

clean:
	find . -name "instance" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf results
