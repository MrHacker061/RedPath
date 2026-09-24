"""Learner-controlled terminal lifecycle boundary; no SSH implementation yet."""


def open_terminal(session_id: str) -> str:
    raise NotImplementedError("Kali terminal creation is not implemented")


def resize_terminal(terminal_id: str, columns: int, rows: int) -> None:
    raise NotImplementedError("Kali terminal resizing is not implemented")


def close_terminal(terminal_id: str) -> None:
    raise NotImplementedError("Kali terminal closing is not implemented")
