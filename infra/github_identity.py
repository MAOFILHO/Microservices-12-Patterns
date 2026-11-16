#!/usr/bin/env python3
"""make github-identity — the Azure identity the "Deploy" GitHub workflow signs in as (pattern 3).

Creates, only where missing:
  1. an app registration named APP_NAME, and its service principal;
  2. federated credentials (OIDC) trusting only this repo's main branch, in both subject forms
     GitHub uses, so it signs in with a short-lived token and no client secret exists anywhere;
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from service_table import AZURE_RESOURCE_GROUP  # noqa: E402

APP_NAME = "ms12p-github-deploy"
CREDENTIAL_NAME = "github-main-branch"
ISSUER = "https://token.actions.githubusercontent.com"
RESOURCE_GROUP = AZURE_RESOURCE_GROUP
ROLE = "Contributor"
STEPS = ["app", "service_principal", "credential", "role", "github_secrets"]
GITHUB_SECRETS = ["AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"]


def federated_credentials(repo: str, owner_id: int, repo_id: int) -> list[dict]:
    """The subjects GitHub may present for a run on main of this repo: the name-only form, and the
    form with account and repo ids that GitHub sends for newer repos (seen on the first real
    Deploy run). The id form also survives a rename and rejects a re-created repo of the same name."""
    owner, name = repo.split("/")
    subjects = {
        CREDENTIAL_NAME: f"repo:{repo}:ref:refs/heads/main",
        f"{CREDENTIAL_NAME}-ids": f"repo:{owner}@{owner_id}/{name}@{repo_id}:ref:refs/heads/main",
    }
    return [{"name": cred_name, "issuer": ISSUER, "subject": subject, "audiences": ["api://AzureADTokenExchange"],
             "description": "GitHub Actions on main of this repo only (Deploy workflow)."}
            for cred_name, subject in subjects.items()]


def missing_credentials(wanted: list[dict], existing_names: list[str]) -> list[dict]:
    return [cred for cred in wanted if cred["name"] not in existing_names]


def role_scope(subscription_id: str, resource_group: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"


def missing_steps(found: dict) -> list[str]:
    """What still needs creating. The role needs the resource group, which only exists while
    provisioned. A newly created app has a new client id, so the GitHub secrets are rewritten."""
    todo = [step for step in STEPS if not found[step] and (step != "role" or found["resource_group"])]
    if "app" in todo and "github_secrets" not in todo:
        todo.append("github_secrets")
    return todo


def role_assignment_args(sp_object_id: str, scope: str) -> list[str]:
    """By object id: right after creating a service principal, Entra has often not replicated it,
    and an assignment by app id fails with "cannot find principal"."""
    return ["role", "assignment", "create", "--assignee-object-id", sp_object_id,
            "--assignee-principal-type", "ServicePrincipal", "--role", ROLE, "--scope", scope]


def pick_app(apps: list[dict]) -> str | None:
    """`az ad app list --display-name` matches by prefix: keep only the exact name."""
    return next((app["appId"] for app in apps if app["displayName"] == APP_NAME), None)


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
    return pick_app(_az_json(["ad", "app", "list", "--display-name", APP_NAME]) or [])


def sp_object_id(client_id: str) -> str | None:
    principals = _az_json(["ad", "sp", "list", "--filter", f"appId eq '{client_id}'"]) or []
    return principals[0]["id"] if principals else None


def grant_role_if_identity_exists(subscription_id: str, resource_group: str) -> None:
    """Called by make provision right after it creates the resource group."""
    client_id = app_id()
    object_id = sp_object_id(client_id) if client_id else None
    if object_id is None:
        return
    scope = role_scope(subscription_id, resource_group)
    if not _az_json(["role", "assignment", "list", "--assignee", object_id, "--role", ROLE, "--scope", scope]):
        _run(["az", *role_assignment_args(object_id, scope)])
        print(f"Deploy identity {APP_NAME}: {ROLE} granted on {resource_group}.")


def main() -> int:
    account = _az_json(["account", "show"])
    subscription_id, tenant_id = account["id"], account["tenantId"]
    repo = repo_from_remote(_run(["git", "remote", "get-url", "origin"]))
    scope = role_scope(subscription_id, RESOURCE_GROUP)

    client_id = app_id()
    object_id = sp_object_id(client_id) if client_id else None
    owner_id, repo_id = (int(v) for v in _run(["gh", "api", f"repos/{repo}", "--jq", ".owner.id, .id"]).split())
    wanted = federated_credentials(repo, owner_id, repo_id)
    secret_names = {item["name"] for item in json.loads(_run(["gh", "secret", "list", "--repo", repo, "--json", "name"]) or "[]")}
    found = {
        "app": client_id is not None,
        "service_principal": object_id is not None,
        "credential": bool(client_id) and not missing_credentials(
            wanted, [c["name"] for c in _az_json(["ad", "app", "federated-credential", "list", "--id", client_id])]),
        "resource_group": _run(["az", "group", "exists", "--name", RESOURCE_GROUP]) == "true",
        "role": False,
        "github_secrets": set(GITHUB_SECRETS) <= secret_names,
    }
    if object_id and found["resource_group"]:
        found["role"] = bool(_az_json(["role", "assignment", "list", "--assignee", object_id, "--role", ROLE, "--scope", scope]))

    todo = missing_steps(found)
    print(f"Repo {repo}, identity {APP_NAME}. To create: {', '.join(todo) or 'nothing, already set up'}.")
    if "app" in todo:
        client_id = _az_json(["ad", "app", "create", "--display-name", APP_NAME])["appId"]
    if "service_principal" in todo:
        object_id = _az_json(["ad", "sp", "create", "--id", client_id])["id"]
    if "credential" in todo:
        existing = [c["name"] for c in _az_json(["ad", "app", "federated-credential", "list", "--id", client_id]) or []]
        for cred in missing_credentials(wanted, existing):
            _run(["az", "ad", "app", "federated-credential", "create", "--id", client_id,
                  "--parameters", json.dumps(cred)])
    if "role" in todo:
        _run(["az", *role_assignment_args(object_id, scope)])
    if not found["resource_group"]:
        print(f"{RESOURCE_GROUP} does not exist yet: make provision grants the role when it creates it.")
    if "github_secrets" in todo:
        # Not passwords, but masked in this public repo's logs, and passed on stdin so they never
        # show in the process list.
        for name, value in zip(GITHUB_SECRETS, [client_id, tenant_id, subscription_id]):
            subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value, text=True, check=True,
                           capture_output=True)
        print(f"GitHub secrets {', '.join(GITHUB_SECRETS)} are set.")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
