"""Base notifier interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    @abstractmethod
    def send(self, subject: str, body_html: str, body_text: str) -> bool:
        """Send a notification. Returns True on success."""
