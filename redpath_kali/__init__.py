"""Planned Kali-container terminal boundary; no SSH implementation yet."""

from .terminal import close_terminal, open_terminal, resize_terminal

__all__ = ["open_terminal", "resize_terminal", "close_terminal"]
