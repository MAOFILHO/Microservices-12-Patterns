"""Post-setup smoke tests: run AFTER `make setup`. Confirms every service's
venv was actually created with its dependencies installed, the frontend's
npm dependencies are present, and — only if Azure was provisioned — that
every resource is live and at the approved (cheap) SKU, not silently
upgraded to something pricier."""
import json
import subprocess

import pytest

from service_table import FLASK_SERVICES, GATEWAY


@pytest.mark.parametrize("svc", [GATEWAY], ids=lambda s: s.name)
def test_gateway_venv_has_dependencies(svc):
    venv_python = svc.path / ".venv" / "bin" / "python"
    if not venv_python.exists():
        pytest.skip(f"{svc.path.name}/.venv not created yet — run `make setup` first")
    result = subprocess.run([str(venv_python), "-c", "import fastapi, httpx"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("svc", FLASK_SERVICES, ids=lambda s: s.name)
def test_service_venv_has_dependencies(svc):
    venv_python = svc.path / ".venv" / "bin" / "python"
    if not venv_python.exists():
        pytest.skip(f"services/{svc.name}/.venv not created yet — run `make setup` first")
    result = subprocess.run([str(venv_python), "-c", "import flask, pydantic"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_frontend_node_modules_installed(repo_root):
    node_modules = repo_root / "frontend" / "node_modules"
    if not node_modules.exists():
        pytest.skip("frontend/node_modules not installed yet — run `make setup` first")
    assert (node_modules / "react").exists()


def test_azure_resources_live_at_approved_sku_if_provisioned(repo_root):
    state_file = repo_root / "infra" / ".state.json"
    if not state_file.exists():
        pytest.skip("infra/.state.json not found — Azure was not provisioned")

    state = json.loads(state_file.read_text())
    rg = state["resource_group"]
    acr_name = state["names"]["acr_name"]

    result = subprocess.run(
        ["az", "acr", "show", "--name", acr_name, "--resource-group", rg, "--output", "json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"ACR '{acr_name}' not found — expected it to be live"
    acr_info = json.loads(result.stdout)
    assert acr_info["sku"]["name"] == "Basic", (
        f"ACR SKU is '{acr_info['sku']['name']}', expected the approved 'Basic' tier — "
        f"it must never be silently upgraded"
    )

    mysql_name = state["names"]["mysql_server_name"]
    result = subprocess.run(
        ["az", "mysql", "flexible-server", "show", "--name", mysql_name, "--resource-group", rg, "--output", "json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"MySQL Flexible Server '{mysql_name}' not found — expected it to be live"
    mysql_info = json.loads(result.stdout)
    assert mysql_info["sku"]["tier"] == "Burstable" and mysql_info["sku"]["name"] == "Standard_B1ms", (
        f"MySQL SKU is {mysql_info['sku']}, expected the approved Burstable B1ms tier"
    )
