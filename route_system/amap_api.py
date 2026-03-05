"""
高德地图 API 封装
"""
import requests
import time
from typing import Optional, List, Tuple


class AmapAPI:
    def __init__(self, key: str, delay: float = 0.5):
        self.key = key
        self.delay = delay

    def geocode(self, address: str, city: str = "重庆") -> Optional[Tuple[float, float]]:
        url = "https://restapi.amap.com/v3/geocode/geo"
        params = {"address": address, "city": city, "key": self.key}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("status") == "1" and data.get("geocodes"):
                loc = data["geocodes"][0]["location"]
                lng, lat = loc.split(",")
                return float(lng), float(lat)
        except Exception as e:
            print(f"  [geocode] 失败: {e}")
        return None

    def driving_route(self, o_lng, o_lat, d_lng, d_lat, retries=3
                      ) -> Optional[dict]:
        """返回 {distance_m, duration_s, polyline: [(lat,lng),...]}"""
        url = "https://restapi.amap.com/v3/direction/driving"
        params = {
            "origin": f"{o_lng},{o_lat}",
            "destination": f"{d_lng},{d_lat}",
            "key": self.key, "extensions": "all", "strategy": 0,
        }
        for attempt in range(retries):
            try:
                resp = requests.get(url, params=params, timeout=15)
                data = resp.json()
                if data.get("status") != "1":
                    return None
                path = data["route"]["paths"][0]
                polyline = []
                for step in path["steps"]:
                    for p in step["polyline"].split(";"):
                        lng, lat = p.split(",")
                        polyline.append((float(lat), float(lng)))
                return {
                    "distance_m": int(path["distance"]),
                    "duration_s": int(path["duration"]),
                    "polyline": polyline,
                }
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    print(f"  [driving] 失败: {e}")
                    return None
        return None

    def driving_polyline(self, o_lng, o_lat, d_lng, d_lat
                         ) -> List[Tuple[float, float]]:
        """简化接口: 只返回路线坐标 [(lat,lng),...]"""
        result = self.driving_route(o_lng, o_lat, d_lng, d_lat)
        time.sleep(self.delay)
        return result["polyline"] if result else []
