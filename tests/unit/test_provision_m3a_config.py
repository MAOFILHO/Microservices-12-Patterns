"""#6: the M3a features get what they need in Azure: a bus, the inventory address, a signing key.

Checked against the compiled template and provision's arguments. No Azure calls, no spend.
"""
import base64
import json
import shutil
import subprocess

import pytest

import provision


def test_signing_key_is_a_fresh_rsa_private_key_in_one_line():
    first, second = provision.generate_jwt_key_b64(), provision.generate_jwt_key_b64()
    assert "\n" not in first and first != second
    assert base64.b64decode(first).decode().startswith("-----BEGIN PRIVATE KEY-----")


def test_signing_key_never_reaches_the_console():
    params = provision.bicep_parameters("eastus", {"acr_name": "a", "log_analytics_name": "l",
                                                   "static_web_app_name": "w", "mysql_server_name": "m"},
                                        "pw", keep_warm=False, tag="t", jwt_key_b64="SECRETKEY")
    printed = " ".join(provision._redact_secrets(params))
    assert "SECRETKEY" not in printed and "pw" not in printed.split("mysqlAdminPassword=")[1][:3]


def test_redis_is_imported_into_our_registry_for_linux_amd64():
    args = provision.redis_import_args("rg", "myacr")
    assert args[args.index("--source") + 1] == f"docker.io/library/{provision.REDIS_IMAGE}"
    assert args[args.index("--image") + 1] == provision.REDIS_IMAGE


@pytest.fixture(scope="module")
def template():
    if shutil.which("az") is None:
        pytest.skip("Azure CLI not installed")
    out = subprocess.run(["az", "bicep", "build", "--file", str(provision.BICEP_FILE), "--stdout"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _app(template, name):
    """The compiled module for one Container App, with its parameters as plain values."""
    for resource in template["resources"]:
        if resource.get("name") == name and resource["type"] == "Microsoft.Resources/deployments":
            return resource["properties"]["parameters"]
    raise AssertionError(f"no module {name}")


def _env_names(template, name):
    env = _app(template, name)["envVars"]["value"]
    text = json.dumps(env)
    return text


def test_redis_is_internal_tcp_only(template):
    redis = _app(template, "redis")
    assert redis["external"]["value"] is False
    assert redis["transport"]["value"] == "tcp"
    assert redis["targetPort"]["value"] == 6379


def test_order_and_inventory_get_the_bus_and_order_gets_inventory(template):
    order, inventory = _env_names(template, "order"), _env_names(template, "inventory")
    assert "REDIS_URL" in order and "REDIS_URL" in inventory
    assert "INVENTORY_SERVICE_BASE_URL" in order


def test_user_reads_its_signing_key_from_a_secret(template):
    user = _app(template, "user")
    assert "JWT_PRIVATE_KEY_B64" in json.dumps(user["envVars"]["value"])
    assert "secretRef" in json.dumps(user["envVars"]["value"])
