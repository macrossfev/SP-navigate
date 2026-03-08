"""Amap (Gaode) driving distance and route provider."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional, Tuple

import requests

from .base import DistanceProvider, DistanceResult

if TYPE_CHECKING:
    from navigate.core.models import Point


class AmapProvider(DistanceProvider):
    """Distance calculation using Amap driving route API.

    Provides real driving distance, duration, and route polylines.
    Requires a valid Amap Web Services API key.
    """

    API_BASE = "https://restapi.amap.com/v3"

    def __init__(self, api_key: str, request_delay: float = 0.5,
                 timeout: int = 15, retries: int = 3):
        self._key = api_key
        self._delay = request_delay
        self._timeout = timeout
        self._retries = retries
        self._last_request_time = 0.0

    @property
    def name(self) -> str:
        return "amap"

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_request_time = time.time()

    def get_distance(self, origin: "Point", destination: "Point") -> DistanceResult:
        route = self._driving_route(origin.lng, origin.lat,
                                     destination.lng, destination.lat)
        if route:
            return DistanceResult(
                distance_km=route["distance_m"] / 1000,
                duration_min=route["duration_s"] / 60,
                polyline=route.get("polyline", []),
            )
        # Fallback: straight-line estimate
        from .haversine import haversine
        dist = haversine(origin.lat, origin.lng, destination.lat, destination.lng)
        return DistanceResult(distance_km=dist, duration_min=dist / 35 * 60)

    def get_polyline(self, origin: "Point", destination: "Point") -> list:
        self._throttle()
        route = self._driving_route(origin.lng, origin.lat,
                                     destination.lng, destination.lat)
        return route.get("polyline", []) if route else []

    def geocode(self, address: str, city: str = "") -> Optional[Tuple[float, float]]:
        """Geocode an address to (lng, lat) coordinates."""
        self._throttle()
        params = {"key": self._key, "address": address, "output": "json"}
        if city:
            params["city"] = city
        try:
            resp = requests.get(f"{self.API_BASE}/geocoding/geo",
                                params=params, timeout=10)
            data = resp.json()
            if data.get("status") == "1" and data.get("geocodes"):
                loc = data["geocodes"][0]["location"]
                lng, lat = loc.split(",")
                return float(lng), float(lat)
        except Exception:
            pass
        return None

    def _driving_route(self, o_lng, o_lat, d_lng, d_lat) -> Optional[dict]:
        params = {
            "key": self._key,
            "origin": f"{o_lng},{o_lat}",
            "destination": f"{d_lng},{d_lat}",
            "extensions": "all",
            "output": "json",
        }
        for attempt in range(self._retries):
            try:
                self._throttle()
                resp = requests.get(f"{self.API_BASE}/direction/driving",
                                    params=params, timeout=self._timeout)
                data = resp.json()
                if data.get("status") == "1" and data.get("route", {}).get("paths"):
                    path = data["route"]["paths"][0]
                    polyline = []
                    for step in path.get("steps", []):
                        for pair in step.get("polyline", "").split(";"):
                            if "," in pair:
                                lng, lat = pair.split(",")
                                polyline.append((float(lat), float(lng)))
                    return {
                        "distance_m": float(path["distance"]),
                        "duration_s": float(path["duration"]),
                        "polyline": polyline,
                    }
            except Exception:
                if attempt < self._retries - 1:
                    time.sleep(2)
        return None
