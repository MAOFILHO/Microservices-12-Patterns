"""#8: the Azure identity GitHub Actions deploys with. These test what the script would do,
without touching Azure: the owner runs the real thing."""
import github_identity as gi


def test_only_this_repos_main_branch_can_sign_in_as_it():
    cred = gi.federated_credential("MAOFILHO/Microservices-12-Patterns")
    assert cred["issuer"] == "https://token.actions.githubusercontent.com"
    assert cred["subject"] == "repo:MAOFILHO/Microservices-12-Patterns:ref:refs/heads/main"
    assert cred["audiences"] == ["api://AzureADTokenExchange"]


def test_access_is_this_resource_group_only_never_the_subscription():
    scope = gi.role_scope("sub-123", "rg-microservices-12-patterns")
    assert scope == "/subscriptions/sub-123/resourceGroups/rg-microservices-12-patterns"


def test_first_run_creates_everything():
    found = {"app": False, "service_principal": False, "credential": False, "resource_group": True, "role": False}
    assert gi.missing_steps(found) == ["app", "service_principal", "credential", "role"]


def test_second_run_changes_nothing():
    found = {"app": True, "service_principal": True, "credential": True, "resource_group": True, "role": True}
    assert gi.missing_steps(found) == []


def test_role_waits_for_the_resource_group():
    """After make teardown the group is gone; make provision grants the role again."""
    found = {"app": True, "service_principal": True, "credential": True, "resource_group": False, "role": False}
    assert gi.missing_steps(found) == []


def test_repo_is_read_from_the_git_remote():
    assert gi.repo_from_remote("https://github.com/MAOFILHO/Microservices-12-Patterns.git") == "MAOFILHO/Microservices-12-Patterns"
    assert gi.repo_from_remote("git@github.com:MAOFILHO/Microservices-12-Patterns.git") == "MAOFILHO/Microservices-12-Patterns"
