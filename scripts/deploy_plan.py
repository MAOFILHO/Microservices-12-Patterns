#!/usr/bin/env python3
"""Which services the Deploy workflow rebuilds (pattern 3): those whose code changed since the
commit they are running now. Uses the same rules as CI (ci_changes.plan), so a shared/ change
rebuilds every service.

CLI: `deploy_plan.py <head-commit>` reads {"service": "running-commit-or-null"} as JSON on stdin and
prints the services to deploy, one per line.
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_changes import plan  # noqa: E402
from service_table import REPO_ROOT  # noqa: E402


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
        if files is None or service in {image["image"] for image in plan(files)["images"]}:
            deploy.append(service)
    return deploy


def image_size_mb(manifest: dict) -> int:
    """Compressed size of a single-platform image: its config plus every layer."""
    total = manifest["config"]["size"] + sum(layer["size"] for layer in manifest["layers"])
    return round(total / (1024 * 1024))


def git_changed_since(commit: str) -> list[str]:
    result = subprocess.run(["git", "diff", "--name-only", f"{commit}...HEAD"], cwd=REPO_ROOT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise LookupError(commit)
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    if sys.argv[1:2] == ["--size"]:
        print(image_size_mb(json.load(sys.stdin)))
        return 0
    head = sys.argv[1]
    running = json.load(sys.stdin)
    print("\n".join(services_to_deploy(running, head, git_changed_since)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
