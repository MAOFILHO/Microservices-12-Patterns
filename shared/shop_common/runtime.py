"""Facts about the running process (pattern 9). No Flask or FastAPI import, so both can use it."""
import os


def runtime_info(service_name: str, instance: str) -> dict:
    """Facts about the running process, for the Containerization page. Never the user name."""
    import platform
    from pathlib import Path

    uid = os.getuid() if hasattr(os, "getuid") else None
    return {
        "service": service_name,
        "instance": instance,
        "uid": uid,
        "root": uid == 0,
        "in_container": Path("/.dockerenv").exists() or bool(os.environ.get("CONTAINER_APP_NAME")),
        "os": platform.system(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "git_sha": os.environ.get("GIT_SHA", "local"),
        # Set by the Deploy workflow from the registry's manifest; unknown otherwise.
        "image_size_mb": int(os.environ["IMAGE_SIZE_MB"]) if os.environ.get("IMAGE_SIZE_MB", "").isdigit() else None,
    }
