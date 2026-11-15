"""Review fixes: re-running provision must not break or log out a live stack."""
import json

import pytest

import provision


def test_a_normal_provision_deploys_the_commit_it_just_built():
    assert provision.choose_image_tag(skip_build=False, head="new", previous="old") == "new"


def test_skip_build_reuses_the_images_built_last_time():
    """Pointing apps at a tag that was never built would make every image pull fail."""
    assert provision.choose_image_tag(skip_build=True, head="new", previous="old") == "old"


def test_skip_build_without_a_previous_build_stops_with_a_clear_message():
    with pytest.raises(SystemExit, match="without --skip-build"):
        provision.choose_image_tag(skip_build=True, head="new", previous=None)


def test_a_rerun_keeps_the_signing_key_so_nobody_is_logged_out():
    assert provision.choose_jwt_key(previous="KEEP") == "KEEP"
    assert provision.choose_jwt_key(previous=None) != provision.choose_jwt_key(previous=None)


def test_image_sizes_reach_every_app():
    params = provision.bicep_parameters("eastus", {"acr_name": "a", "log_analytics_name": "l",
                                                   "static_web_app_name": "w", "mysql_server_name": "m"},
                                        "pw", keep_warm=False, tag="t", jwt_key_b64="K",
                                        image_sizes={"user": 61, "gateway": 70})
    sizes = next(p for p in params if p.startswith("imageSizesMb="))
    assert json.loads(sizes.split("=", 1)[1]) == {"user": 61, "gateway": 70}
