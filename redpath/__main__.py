"""Supported RedPath API launcher with enforced loopback binding."""

import uvicorn

from redpath.config import get_settings


def main() -> None:
    settings = get_settings()  # Settings rejects non-loopback hosts.
    uvicorn.run("redpath.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
