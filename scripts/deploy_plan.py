#!/usr/bin/env python3
"""Which services the Deploy workflow rebuilds (pattern 3): those whose code changed since the
commit they are running now. Uses the same rules as CI (ci_changes.plan), so a shared/ change
rebuilds every service, minus CI-only files, which rebuild nothing.

CLI, used by .github/workflows/deploy.yml so the workflow hardcodes nothing:
  deploy_plan.py --services         every Azure service and its folder, "name folder" per line
  deploy_plan.py --resource-group   the project's Azure resource group
  deploy_plan.py --size             image size in MB, from `az acr manifest show` JSON on stdin
  deploy_plan.py <head-commit>      reads {"service": "running-commit-or-null"} JSON on stdin and
                                    prints the services to deploy, one per line
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_changes import plan  # noqa: E402
from service_table import AZURE_RESOURCE_GROUP, AZURE_SERVICES, REPO_ROOT  # noqa: E402


def services_to_deploy(running: dict[str, str | None], head: str,
                       changed_since: Callable[[str], list[str]]) -> list[str]:
    deploy = []
    for service, commit in sorted(running.items()):
        if commit == head:
            continue
        try:
            files = changed_since(commit) if commit else None
        except LookupError:  # a commit this checkout does not know: rebuild to be safe
            files = None
        if files is None or service in {image["image"] for image in plan(files, for_deploy=True)["images"]}:
            deploy.append(service)
    return deploy


def image_size_mb(manifest: dict) -> int | None:
    """Compressed size of a single-platform image: its config plus every layer. None for a
    multi-platform index, which has no layers of its own (the page then shows "unknown")."""
    if "layers" not in manifest or "config" not in manifest:
        return None
    total = manifest["config"]["size"] + sum(layer["size"] for layer in manifest["layers"])
    return round(total / (1024 * 1024))


def git_changed_since(commit: str) -> list[str]:
    result = subprocess.run(["git", "diff", "--name-only", f"{commit}...HEAD"], cwd=REPO_ROOT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise LookupError(commit)
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    if sys.argv[1:2] == ["--services"]:
        print("\n".join(f"{s.name} {s.path.relative_to(REPO_ROOT).as_posix()}" for s in AZURE_SERVICES))
        return 0
    if sys.argv[1:2] == ["--resource-group"]:
        print(AZURE_RESOURCE_GROUP)
        return 0
    if sys.argv[1:2] == ["--size"]:
        size = image_size_mb(json.load(sys.stdin))
        print("" if size is None else size)
        return 0
    head = sys.argv[1]
    running = json.load(sys.stdin)
    print("\n".join(services_to_deploy(running, head, git_changed_since)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
