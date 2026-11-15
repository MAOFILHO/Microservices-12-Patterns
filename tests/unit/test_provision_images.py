"""#5: Azure images are tagged with the commit they were built from, and the local-only registry
is never built for Azure. No Azure calls: these test the arguments provision would send."""
import subprocess
from pathlib import Path

import provision


def test_azure_builds_every_service_and_the_gateway_but_not_the_registry():
    assert set(provision.AZURE_SERVICES) == {"user", "catalog", "order", "payment", "inventory", "gateway"}


def test_image_tag_is_the_current_commit(repo_root):
    head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=repo_root,
                          capture_output=True, text=True, check=True).stdout.strip()
    assert provision.image_tag() == head


def test_acr_build_tags_the_image_and_passes_the_commit_inside():
    args = provision.acr_build_args("rg", "myacr", "order", Path("/src/order"), "abc123def456")
    assert args[args.index("--image") + 1] == "order:abc123def456"
    assert args[args.index("--build-arg") + 1] == "GIT_SHA=abc123def456"
    assert args[args.index("--platform") + 1] == "linux/amd64"
    assert args[-1] == "/src/order"


def test_bicep_deploys_that_same_tag():
    params = provision.bicep_parameters("eastus", {"acr_name": "a", "log_analytics_name": "l",
                                                   "static_web_app_name": "w", "mysql_server_name": "m"},
                                        "pw", keep_warm=False, tag="abc123def456", jwt_key_b64="K")
    assert "imageTag=abc123def456" in params
