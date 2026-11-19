.PHONY: setup run github-identity provision pause resume teardown verify test contracts smoke flash-sale clean

setup:
	python3.12 scripts/setup.py

run:
	python3.12 scripts/run_local.py

# Once, by the owner (#8): the Azure identity the Deploy workflow signs in as. No secrets created.
github-identity:
	python3.12 infra/github_identity.py

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
	registry/.venv/bin/python -m pytest registry/tests -v

# Pattern 11 only: the order service writes its contracts, then payment and catalog verify them.
contracts:
	services/order/.venv/bin/python -m pytest services/order/tests/test_contracts_consumer.py -v
	services/payment/.venv/bin/python -m pytest services/payment/tests/test_contract_provider.py -v
	services/catalog/.venv/bin/python -m pytest services/catalog/tests/test_contract_provider.py -v

smoke:
	.venv/bin/python -m pytest tests/smoke -v

# Demo 15, Azure only: the same flash sale under a replica cap. Run CAP=3, then CAP=8.
flash-sale:
	.venv/bin/python infra/autoscale_demo.py --cap $(CAP) $(ARGS)

clean:
	find . -name "instance" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf results
