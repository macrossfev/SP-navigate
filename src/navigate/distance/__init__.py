"""Distance providers."""
from .base import DistanceProvider, DistanceResult
from .haversine import HaversineProvider, haversine
from .amap import AmapProvider

PROVIDERS = {
    "haversine": HaversineProvider,
    "amap": AmapProvider,
}

__all__ = ["DistanceProvider", "DistanceResult", "HaversineProvider",
           "AmapProvider", "haversine", "PROVIDERS"]
