"""#6: Redis holds undelivered events in memory, so resume must bring it back as exactly one
always-on replica, while the services may scale to zero. And provision records it for pause."""
import provision
import resume


def test_resume_keeps_redis_at_exactly_one_replica():
    assert resume.replica_args("redis") == ["--min-replicas", "1", "--max-replicas", "1"]


def test_resume_lets_services_scale_to_zero():
    assert resume.replica_args("order")[:2] == ["--min-replicas", "0"]


def test_provision_records_redis_so_pause_scales_it_down():
    assert "redis" in provision.container_apps_for_state()
