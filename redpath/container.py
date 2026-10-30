"""Linux container launcher; the host-side port mapping is the loopback boundary."""

from redpath.config import get_settings
# The same marker files the Ollama address rule uses to allow Docker's host
# address (see redpath_ai/providers.py), so both checks agree on "in a container".
from redpath_ai.providers import CONTAINER_MARKERS


def _require_container() -> None:
    # Binding all interfaces is only safe inside a container network namespace,
    # where compose publishes the port on 127.0.0.1 alone.
    if not any(marker.exists() for marker in CONTAINER_MARKERS):
        raise SystemExit("redpath.container must run inside a container; use `python -m redpath` on Windows")


def main() -> None:
    _require_container()
    import uvicorn

    from redpath.app import create_app

    settings = get_settings()
    # The browser sends Host: 127.0.0.1:<published port>, so the container port
    # must equal the host port for LocalRequestProtection to accept requests.
    uvicorn.run(
        create_app(settings), host="0.0.0.0", port=settings.port, workers=1,
        log_config=None, access_log=False, timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()
