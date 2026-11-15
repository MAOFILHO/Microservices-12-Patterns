"""#9: the Deploy button rebuilds only services whose code changed since the commit they run."""
from deploy_plan import image_size_mb, services_to_deploy

ALL = ["catalog", "gateway", "inventory", "order", "payment", "user"]


def _changes(files_by_commit):
    def changed_since(commit):
        if commit not in files_by_commit:
            raise LookupError(commit)
        return files_by_commit[commit]
    return changed_since


def test_services_already_on_this_commit_are_left_alone():
    running = {name: "abc" for name in ALL}
    assert services_to_deploy(running, "abc", _changes({})) == []


def test_only_the_service_that_changed_is_rebuilt():
    running = {name: "old" for name in ALL}
    assert services_to_deploy(running, "new", _changes({"old": ["services/payment/application/routes.py"]})) == ["payment"]


def test_a_shared_change_rebuilds_everything():
    running = {name: "old" for name in ALL}
    assert services_to_deploy(running, "new", _changes({"old": ["shared/shop_common/events.py"]})) == ALL


def test_unknown_or_unparseable_running_versions_are_rebuilt():
    """Never deployed by commit yet ('latest'), or a commit this checkout does not know."""
    running = {name: "abc" for name in ALL} | {"user": None, "order": "gone"}
    assert services_to_deploy(running, "abc", _changes({})) == ["order", "user"]


def test_image_size_is_the_sum_of_its_layers():
    manifest = {"config": {"size": 1_000_000}, "layers": [{"size": 30_000_000}, {"size": 20_428_800}]}
    assert image_size_mb(manifest) == 49


def test_a_ci_only_change_rebuilds_nothing():
    running = {name: "old" for name in ALL}
    changed = _changes({"old": [".github/workflows/ci.yml", "scripts/ci_changes.py", "pytest.ini"]})
    assert services_to_deploy(running, "new", changed) == []


def test_a_multi_platform_index_reports_unknown_size_instead_of_crashing():
    index = {"mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [{"size": 1}]}
    assert image_size_mb(index) is None
