"""Amap geocoding provider."""
from __future__ import annotations

from typing import Optional, Tuple

from .base import GeocodingProvider


class AmapGeocoder(GeocodingProvider):
    """Geocoding using Amap Web Services API."""

    def __init__(self, api_key: str):
        # Reuse the distance provider's geocoding capability
        from navigate.distance.amap import AmapProvider
        self._provider = AmapProvider(api_key=api_key)

    def geocode(self, address: str, city: str = "") -> Optional[Tuple[float, float]]:
        return self._provider.geocode(address, city)
