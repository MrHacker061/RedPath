"""Host-side Docker Compose lifecycle boundary; not implemented yet."""


def check_prerequisites() -> None:
    raise NotImplementedError("Desktop prerequisite checks are not implemented")


def start_stack() -> None:
    raise NotImplementedError("Compose startup is not implemented")


def stop_stack() -> None:
    raise NotImplementedError("Compose shutdown is not implemented")


def service_health() -> dict[str, str]:
    raise NotImplementedError("Compose health inspection is not implemented")
