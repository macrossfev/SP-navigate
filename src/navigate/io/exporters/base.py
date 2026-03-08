"""Abstract exporter."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from navigate.core.models import PlanResult
    from navigate.core.config import NavigateConfig


class BaseExporter(ABC):
    """Abstract interface for exporting plan results."""

    def __init__(self, config: "NavigateConfig"):
        self.config = config

    @abstractmethod
    def export(self, result: "PlanResult", output_dir: str, **kwargs) -> str:
        """Export results and return the output file path."""
        ...
