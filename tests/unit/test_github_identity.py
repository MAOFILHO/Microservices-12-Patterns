"""#8: the Azure identity GitHub Actions deploys with. These test what the script would do,
without touching Azure: the owner runs the real thing."""
import github_identity as gi


def test_only_this_repos_main_branch_can_sign_in_as_it():
    """GitHub may send the name-only subject or the one with account and repo ids (newer repos;
    seen on the first real Deploy run). Both are trusted, both for main of this repo only."""
    creds = gi.federated_credentials("MAOFILHO/Microservices-12-Patterns", owner_id=69284062, repo_id=1458985608)
    assert [c["subject"] for c in creds] == [
        "repo:MAOFILHO/Microservices-12-Patterns:ref:refs/heads/main",
        "repo:MAOFILHO@69284062/Microservices-12-Patterns@1458985608:ref:refs/heads/main",
    ]
    assert len({c["name"] for c in creds}) == 2
    for cred in creds:
        assert cred["issuer"] == "https://token.actions.githubusercontent.com"
        assert cred["audiences"] == ["api://AzureADTokenExchange"]


def test_a_missing_second_credential_is_added_on_the_next_run():
    creds = gi.federated_credentials("o/r", owner_id=1, repo_id=2)
    existing = [creds[0]["name"]]
    assert gi.missing_credentials(creds, existing) == [creds[1]]
    assert gi.missing_credentials(creds, [c["name"] for c in creds]) == []


def test_access_is_this_resource_group_only_never_the_subscription():
    scope = gi.role_scope("sub-123", "rg-microservices-12-patterns")
    assert scope == "/subscriptions/sub-123/resourceGroups/rg-microservices-12-patterns"


NOTHING = {"app": False, "service_principal": False, "credential": False, "resource_group": True,
           "role": False, "github_secrets": False}
ALL = {step: True for step in NOTHING}


def test_first_run_creates_everything():
    assert gi.missing_steps(NOTHING) == ["app", "service_principal", "credential", "role", "github_secrets"]


def test_second_run_changes_nothing():
    """Not even the GitHub secrets are rewritten."""
    assert gi.missing_steps(ALL) == []


def test_a_new_app_rewrites_the_secrets_even_if_old_ones_exist():
    found = NOTHING | {"github_secrets": True}
    assert "github_secrets" in gi.missing_steps(found)


def test_role_waits_for_the_resource_group():
    """After make teardown the group is gone; make provision grants the role again."""
    assert gi.missing_steps(ALL | {"resource_group": False, "role": False}) == []


def test_role_is_granted_by_object_id_so_a_brand_new_identity_works():
    """By app id, Azure often answers "cannot find principal" right after creating the identity."""
    args = gi.role_assignment_args("sp-object-id", "/subscriptions/s/resourceGroups/rg")
    assert args[args.index("--assignee-object-id") + 1] == "sp-object-id"
    assert args[args.index("--assignee-principal-type") + 1] == "ServicePrincipal"
    assert "--assignee" not in args


def test_only_the_app_with_exactly_our_name_is_ours():
    apps = [{"displayName": "ms12p-github-deploy-old", "appId": "x"}, {"displayName": "ms12p-github-deploy", "appId": "y"}]
    assert gi.pick_app(apps) == "y"
    assert gi.pick_app(apps[:1]) is None


def test_repo_is_read_from_the_git_remote():
    assert gi.repo_from_remote("https://github.com/MAOFILHO/Microservices-12-Patterns.git") == "MAOFILHO/Microservices-12-Patterns"
    assert gi.repo_from_remote("git@github.com:MAOFILHO/Microservices-12-Patterns.git") == "MAOFILHO/Microservices-12-Patterns"
