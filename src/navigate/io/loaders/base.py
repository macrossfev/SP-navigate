"""Abstract data loader."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from navigate.core.models import Point
    from navigate.core.config import DataSourceConfig


class BaseLoader(ABC):
    """Abstract interface for loading points from a data source."""

    @abstractmethod
    def load(self, source: "DataSourceConfig") -> List["Point"]:
        """Load points from the configured data source."""
        ...
