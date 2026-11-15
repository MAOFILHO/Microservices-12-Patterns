"""#7: CI runs only what a change touches. ci_changes.plan() turns the changed file list into
the unit-test suites, container images and other jobs to run."""
from ci_changes import plan


def _suites(p):
    return sorted(s["suite"] for s in p["suites"])


def _images(p):
    return sorted(i["image"] for i in p["images"])


def test_a_change_to_one_service_runs_only_that_service():
    p = plan(["services/payment/application/routes.py"])
    assert _suites(p) == ["payment"]
    assert _images(p) == ["payment"]
    assert p["frontend"] is False and p["bicep"] is False


def test_changing_the_consumer_also_runs_every_provider_contract_check():
    p = plan(["services/order/application/saga.py"])
    assert _suites(p) == ["catalog", "inventory", "order", "payment"]
    assert _images(p) == ["order"]


def test_shared_code_runs_everything():
    p = plan(["shared/shop_common/events.py"])
    assert _suites(p) == ["catalog", "gateway", "inventory", "order", "payment", "registry", "repo-root", "user"]
    assert len(_images(p)) == 7 and p["frontend"] and p["bicep"]


def test_the_service_table_and_the_workflow_run_everything():
    for path in ["scripts/service_table.py", ".github/workflows/ci.yml", "contracts/requirements.txt"]:
        assert len(plan([path])["suites"]) == 8, path


def test_a_contract_file_runs_the_consumer_and_that_provider():
    assert _suites(plan(["contracts/pacts/order-inventory.json"])) == ["inventory", "order"]


def test_frontend_infra_and_docs_changes():
    assert plan(["frontend/src/App.tsx"]) == {"suites": [], "images": [], "frontend": True, "bicep": False}
    p = plan(["infra/bicep/main.bicep"])
    assert _suites(p) == ["repo-root"] and p["bicep"]
    assert plan(["README.md", "docs/PLAN.md"]) == {"suites": [], "images": [], "frontend": False, "bicep": False}


def test_matrix_entries_carry_what_the_jobs_need():
    p = plan(["services/order/run.py", "gateway/app/main.py", "registry/app/main.py"])
    order = next(s for s in p["suites"] if s["suite"] == "order")
    assert order == {"suite": "order", "requirements": "services/order/requirements.txt",
                     "tests": "services/order/tests", "shared": "flask", "contracts": True}
    image = next(i for i in p["images"] if i["image"] == "registry")
    assert image == {"image": "registry", "dir": "registry", "port": 8500, "shared": False}
    assert next(i for i in p["images"] if i["image"] == "gateway")["shared"] is True
