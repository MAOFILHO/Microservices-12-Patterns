#!/usr/bin/env python3
"""Which CI jobs a change needs (pattern 3): only the services it touches.

Reads the changed file paths (one per line on stdin) or `--all`, and writes the plan as GitHub
Actions outputs: `suites` and `images` (JSON lists for job matrices), `frontend` and `bicep`
(true/false). The suite and image lists come from scripts/service_table.py, so a new service needs
no CI edit.

Rules:
- shared code, the service table, CI itself or Pact's version: everything runs.
- a service's folder: its unit tests and its image.
- the order service is the contract consumer, so changing it also runs each provider's contract
  check (payment, catalog, inventory); a contract file runs the consumer and that one provider.
- infra/ and scripts/: the repo-root tests; infra/bicep/ also the Bicep compile.
- frontend/ (and the contracts it displays): the frontend build.
- anything else (docs, README, smoke tests that CI does not run): nothing.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_table import CONTRACT_SUITES, PYTHON_SERVICES, REPO_ROOT  # noqa: E402

RUN_EVERYTHING = ("shared/", "scripts/service_table.py", "scripts/ci_changes.py", ".github/workflows/",
                  "contracts/requirements.txt")
CONSUMER = "order"


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _suite(name: str) -> dict:
    if name == "repo-root":
        return {"suite": name, "requirements": "requirements-dev.txt", "tests": "tests/unit", "shared": "",
                "contracts": False}
    svc = next(s for s in PYTHON_SERVICES if s.name == name)
    shared = "" if name == "registry" else ("fastapi" if svc.kind == "fastapi" else "flask")
    return {"suite": name, "requirements": f"{_rel(svc.path)}/requirements.txt", "tests": f"{_rel(svc.path)}/tests",
            "shared": shared, "contracts": name in CONTRACT_SUITES}


def _image(name: str) -> dict:
    svc = next(s for s in PYTHON_SERVICES if s.name == name)
    return {"image": name, "dir": _rel(svc.path), "port": svc.port, "shared": name != "registry"}


def plan(changed: list[str] | None) -> dict:
    """changed=None means run everything (a push to main, a manual run)."""
    every_service = [s.name for s in PYTHON_SERVICES]
    suites: set[str] = set()
    images: set[str] = set()
    frontend = bicep = False

    if changed is None or any(path.startswith(RUN_EVERYTHING) for path in changed):
        suites, images, frontend, bicep = {"repo-root", *every_service}, set(every_service), True, True
    else:
        folders = {_rel(s.path) + "/": s.name for s in PYTHON_SERVICES}
        for path in changed:
            owner = next((name for folder, name in folders.items() if path.startswith(folder)), None)
            if owner:
                suites.add(owner)
                images.add(owner)
                if owner == CONSUMER:
                    suites.update(CONTRACT_SUITES)
            elif path.startswith("contracts/pacts/"):
                provider = Path(path).stem.removeprefix(f"{CONSUMER}-")
                suites.update({CONSUMER, provider} & CONTRACT_SUITES)
                frontend = True  # the Contract Testing page displays these files
            elif path.startswith(("infra/", "scripts/", "tests/unit/", "tests/conftest.py", "requirements-dev.txt")):
                suites.add("repo-root")
                bicep = bicep or path.startswith("infra/bicep/")
            elif path.startswith("frontend/"):
                frontend = True

    return {
        "suites": [_suite(name) for name in sorted(suites)],
        "images": [_image(name) for name in sorted(images)],
        "frontend": frontend,
        "bicep": bicep,
    }


def main() -> int:
    changed = None if "--all" in sys.argv else [line.strip() for line in sys.stdin if line.strip()]
    result = plan(changed)
    lines = [f"suites={json.dumps(result['suites'])}", f"images={json.dumps(result['images'])}",
             f"frontend={str(result['frontend']).lower()}", f"bicep={str(result['bicep']).lower()}"]
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a") as handle:
            handle.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
