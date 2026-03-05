"""
导航轨迹图生成模块
使用 folium 生成标注地图，chromium 截图为 PNG
"""
import os
import subprocess
import folium
from folium import DivIcon
from typing import List, Tuple
from .config import RouteConfig
from .amap_api import AmapAPI
from .data_loader import SamplingPoint
from .strategies.base import DayPlan, PlanResult


class ImageGenerator:
    def __init__(self, config: RouteConfig):
        self.config = config
        self.api = AmapAPI(config.amap_key, config.amap_request_delay)
        self.img_dir = os.path.join(config.output_dir, "images")
        self.html_dir = os.path.join(config.output_dir, "html")
        os.makedirs(self.img_dir, exist_ok=True)
        os.makedirs(self.html_dir, exist_ok=True)

    def generate_all(self, result: PlanResult) -> List[str]:
        """为所有天生成导航图，返回PNG路径列表"""
        print(f"\n[图片生成] 共 {result.total_days} 天...")
        paths = []
        for dp in result.days:
            png = self.generate_day(dp)
            paths.append(png)
        print(f"[图片生成] 完成，保存在 {self.img_dir}")
        return paths

    def generate_day(self, dp: DayPlan) -> str:
        """生成单天的导航图"""
        points = dp.points
        coords = [(p.lat, p.lng) for p in points]

        # 获取驾车路线坐标
        route_pts = []
        if self.config.use_amap_driving and len(coords) >= 2:
            for i in range(len(coords) - 1):
                seg = self.api.driving_polyline(
                    points[i].lng, points[i].lat,
                    points[i + 1].lng, points[i + 1].lat)
                route_pts.extend(seg)

        # 生成HTML
        html_path = os.path.join(self.html_dir, f"第{dp.day}天导航图.html")
        self._create_map(dp.day, points, coords, route_pts, html_path)

        # 截图
        label = "点位图" if not self.config.use_amap_driving else "导航轨迹图"
        png_path = os.path.join(self.img_dir, f"第{dp.day}天{label}.png")
        self._screenshot(html_path, png_path)

        size = os.path.getsize(png_path) // 1024 if os.path.exists(png_path) else 0
        print(f"  第{dp.day}天 [{len(points)}点] → {size}KB")
        return png_path

    @staticmethod
    def _calc_zoom(coords, img_w=1200, img_h=800):
        """根据坐标范围手动计算合适的zoom级别"""
        import math
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        # 加 20% 边距确保标签不被裁切
        lat_range = (max(lats) - min(lats)) * 1.4 or 0.005
        lng_range = (max(lngs) - min(lngs)) * 1.4 or 0.005
        # 每个zoom级别在赤道处的度/像素
        for z in range(18, 5, -1):
            deg_per_px = 360 / (256 * 2**z)
            if lng_range / deg_per_px < img_w and lat_range / deg_per_px < img_h:
                return z
        return 6

    def _create_map(self, day_num, points: List[SamplingPoint],
                    coords: List[Tuple[float, float]],
                    route_pts: List[Tuple[float, float]],
                    html_path: str):
        avg_lat = sum(c[0] for c in coords) / len(coords)
        avg_lng = sum(c[1] for c in coords) / len(coords)
        zoom = self._calc_zoom(coords, self.config.image_width, self.config.image_height)

        m = folium.Map(
            location=[avg_lat, avg_lng], zoom_start=zoom,
            tiles="https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=2&style=8&x={x}&y={y}&z={z}",
            attr="高德地图", width="100%", height="100%",
        )

        if route_pts:
            folium.PolyLine(route_pts, weight=5, color="#0066FF", opacity=0.8).add_to(m)

        n = len(points)
        for i, (pt, coord) in enumerate(zip(points, coords)):
            num = i + 1
            color = "#00AA00" if num == 1 else "#CC0000" if num == n else "#0066FF"
            icon_html = (
                f'<div style="background:{color};color:#fff;border-radius:50%;'
                f'width:28px;height:28px;display:flex;align-items:center;'
                f'justify-content:center;font-size:14px;font-weight:bold;'
                f'border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4)">'
                f'{num}</div>'
            )
            folium.Marker(
                location=[coord[0], coord[1]],
                icon=DivIcon(icon_size=(28, 28), icon_anchor=(14, 14), html=icon_html),
            ).add_to(m)

            label_html = (
                f'<div style="background:rgba(255,255,255,.92);border:1px solid #666;'
                f'border-radius:3px;padding:2px 6px;font-size:12px;font-weight:bold;'
                f'color:#333;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.3)">'
                f'{num}.{pt.short_name}</div>'
            )
            folium.Marker(
                location=[coord[0], coord[1]],
                icon=DivIcon(icon_size=(200, 24), icon_anchor=(-18, 12), html=label_html),
            ).add_to(m)

        # 不使用 fit_bounds（依赖JS异步，无头截图不可靠）
        # zoom已在创建Map时通过 _calc_zoom 手动计算
        m.save(html_path)

        # 注入CSS
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        css = ("<style>html,body{margin:0;padding:0;width:100%;height:100%;"
               "overflow:hidden}.folium-map{position:absolute;top:0;left:0;"
               "right:0;bottom:0}</style>")
        html = html.replace("</head>", css + "</head>")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _screenshot(self, html_path: str, png_path: str):
        w, h = self.config.image_width, self.config.image_height
        cmd = [
            "chromium", "--headless", "--no-sandbox",
            "--disable-gpu", "--disable-software-rasterizer",
            f"--screenshot={png_path}", f"--window-size={w},{h}",
            "--virtual-time-budget=5000", f"file://{html_path}",
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)
