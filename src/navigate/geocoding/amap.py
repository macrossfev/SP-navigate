"""Amap geocoding provider."""
from __future__ import annotations

from typing import Optional, Tuple

from .base import GeocodingProvider


class AmapGeocoder(GeocodingProvider):
    """Geocoding using Amap Web Services API."""

    def __init__(self, api_key: str, request_delay: float = 0.4):
        # Reuse the distance provider's geocoding capability
        # request_delay=0.4 means 400ms between requests (~2.5 req/s, under the 3 QPS limit)
        from navigate.distance.amap import AmapProvider
        self._provider = AmapProvider(api_key=api_key, request_delay=request_delay)

    def geocode(self, address: str, city: str = "") -> Optional[Tuple[float, float]]:
        return self._provider.geocode(address, city)
