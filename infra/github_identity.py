#!/usr/bin/env python3
"""make github-identity — the Azure identity the "Deploy" GitHub workflow signs in as (pattern 3).

Creates, only where missing:
  1. an app registration named APP_NAME, and its service principal;
  2. a federated credential (OIDC) trusting only this repo's main branch, so GitHub signs in with a
     short-lived token and no client secret exists anywhere;
  3. the Contributor role on the project resource group only, never the subscription.

Then stores the three ids (client, tenant, subscription) as GitHub Actions secrets. They are not
passwords, but this repo is public and Actions logs are public: secrets are masked in logs,
variables are not, and the subscription id must never appear in public.

Safe to run again: it changes nothing that already exists. The role assignment disappears with the
resource group on `make teardown`; `make provision` grants it again (grant_role_if_identity_exists).

Runs with the owner's own `az login` and `gh auth`. To remove everything it created:
    az ad app delete --id $(az ad app list --display-name ms12p-github-deploy --query "[0].appId" -o tsv)
    gh secret delete AZURE_CLIENT_ID; gh secret delete AZURE_TENANT_ID; gh secret delete AZURE_SUBSCRIPTION_ID
"""
import json
import re
import subprocess
import sys

APP_NAME = "ms12p-github-deploy"
CREDENTIAL_NAME = "github-main-branch"
ISSUER = "https://token.actions.githubusercontent.com"
RESOURCE_GROUP = "rg-microservices-12-patterns"
ROLE = "Contributor"
STEPS = ["app", "service_principal", "credential", "role"]


def federated_credential(repo: str) -> dict:
    return {
        "name": CREDENTIAL_NAME,
        "issuer": ISSUER,
        "subject": f"repo:{repo}:ref:refs/heads/main",
        "audiences": ["api://AzureADTokenExchange"],
        "description": "GitHub Actions on main of this repo only (Deploy workflow).",
    }


def role_scope(subscription_id: str, resource_group: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"


def missing_steps(found: dict) -> list[str]:
    """What still needs creating. The role needs the resource group, which only exists while provisioned."""
    return [step for step in STEPS if not found[step] and (step != "role" or found["resource_group"])]


def repo_from_remote(url: str) -> str:
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url.strip())
    if not match:
        raise ValueError(f"not a GitHub remote: {url}")
    return match.group(1)


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()


def _az_json(args: list[str]):
    return json.loads(_run(["az", *args, "--output", "json"]) or "null")


def app_id() -> str | None:
    apps = _az_json(["ad", "app", "list", "--display-name", APP_NAME])
    return apps[0]["appId"] if apps else None


def grant_role_if_identity_exists(subscription_id: str, resource_group: str) -> None:
    """Called by make provision right after it creates the resource group."""
    client_id = app_id()
    if client_id is None:
        return
    scope = role_scope(subscription_id, resource_group)
    if not _az_json(["role", "assignment", "list", "--assignee", client_id, "--role", ROLE, "--scope", scope]):
        _run(["az", "role", "assignment", "create", "--assignee", client_id, "--role", ROLE, "--scope", scope])
        print(f"Deploy identity {APP_NAME}: {ROLE} granted on {resource_group}.")


def main() -> int:
    account = _az_json(["account", "show"])
    subscription_id, tenant_id = account["id"], account["tenantId"]
    repo = repo_from_remote(_run(["git", "remote", "get-url", "origin"]))
    scope = role_scope(subscription_id, RESOURCE_GROUP)

    client_id = app_id()
    found = {
        "app": client_id is not None,
        "service_principal": bool(client_id and _az_json(["ad", "sp", "list", "--filter", f"appId eq '{client_id}'"])),
        "credential": bool(client_id and any(c["name"] == CREDENTIAL_NAME for c in
                                             _az_json(["ad", "app", "federated-credential", "list", "--id", client_id]))),
        "resource_group": _run(["az", "group", "exists", "--name", RESOURCE_GROUP]) == "true",
        "role": False,
    }
    if client_id and found["resource_group"]:
        found["role"] = bool(_az_json(["role", "assignment", "list", "--assignee", client_id, "--role", ROLE, "--scope", scope]))

    todo = missing_steps(found)
    print(f"Repo {repo}, identity {APP_NAME}. To create: {', '.join(todo) or 'nothing, already set up'}.")
    if "app" in todo:
        client_id = _az_json(["ad", "app", "create", "--display-name", APP_NAME])["appId"]
    if "service_principal" in todo:
        _run(["az", "ad", "sp", "create", "--id", client_id])
    if "credential" in todo:
        _run(["az", "ad", "app", "federated-credential", "create", "--id", client_id,
              "--parameters", json.dumps(federated_credential(repo))])
    if "role" in todo:
        _run(["az", "role", "assignment", "create", "--assignee", client_id, "--role", ROLE, "--scope", scope])
    if not found["resource_group"]:
        print(f"{RESOURCE_GROUP} does not exist yet: make provision grants the role when it creates it.")

    # The workflow needs these ids to ask Azure for a short-lived token. Stored as secrets so they
    # are masked in public logs; passed on stdin so they never show in the process list.
    for name, value in [("AZURE_CLIENT_ID", client_id), ("AZURE_TENANT_ID", tenant_id),
                        ("AZURE_SUBSCRIPTION_ID", subscription_id)]:
        subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value, text=True, check=True,
                       capture_output=True)
    print("GitHub secrets AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID are set. Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
