"""Review fixes: one place says which services Azure runs, where they live, and the resource group."""
import subprocess
import sys

import github_identity
import provision
import service_table


def test_the_service_table_says_which_services_azure_runs():
    assert [s.name for s in service_table.AZURE_SERVICES] == ["user", "catalog", "order", "payment", "inventory", "gateway"]
    assert set(provision.AZURE_SERVICES) == {s.name for s in service_table.AZURE_SERVICES}


def test_deploy_reads_services_and_folders_from_the_table(repo_root):
    out = subprocess.run([sys.executable, "scripts/deploy_plan.py", "--services"], cwd=repo_root,
                         capture_output=True, text=True, check=True).stdout.split("\n")
    assert "order services/order" in out and "gateway gateway" in out and len([l for l in out if l]) == 6


def test_deploy_provision_and_identity_share_one_resource_group(repo_root):
    out = subprocess.run([sys.executable, "scripts/deploy_plan.py", "--resource-group"], cwd=repo_root,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == provision.DEFAULT_RESOURCE_GROUP == github_identity.RESOURCE_GROUP == service_table.AZURE_RESOURCE_GROUP


def test_no_leftover_services_alias():
    assert not hasattr(provision, "SERVICES")
