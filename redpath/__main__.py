"""Supported RedPath API launcher with enforced loopback binding."""

from redpath.config import get_settings
from redpath.desktop import DesktopHost, _require_windows


def main() -> None:
    _require_windows()
    host = DesktopHost(port=get_settings().port)
    try:
        host.start()
        host.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        host.stop()


if __name__ == "__main__":
    main()
