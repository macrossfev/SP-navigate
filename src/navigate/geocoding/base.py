"""Abstract geocoding provider."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple


class GeocodingProvider(ABC):
    """Abstract interface for address geocoding."""

    @abstractmethod
    def geocode(self, address: str, city: str = "") -> Optional[Tuple[float, float]]:
        """Convert address to (lng, lat) coordinates. Returns None on failure."""
        ...
