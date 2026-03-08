"""Map exporter using folium for interactive maps."""
from __future__ import annotations

import os
import subprocess
from typing import List, Tuple, TYPE_CHECKING

from .base import BaseExporter

if TYPE_CHECKING:
    from navigate.core.models import PlanResult, DayPlan, Point
    from navigate.core.config import NavigateConfig, ExportFormatConfig


class MapExporter(BaseExporter):
    """Generate interactive HTML maps and optional PNG screenshots."""

    def export(self, result: "PlanResult", output_dir: str, **kwargs) -> str:
        import folium
        from folium import DivIcon

        fmt_config: "ExportFormatConfig" = kwargs.get("format_config")
        img_w = fmt_config.image_width if fmt_config else 1200
        img_h = fmt_config.image_height if fmt_config else 800
        output_format = fmt_config.format if fmt_config else "html"

        html_dir = os.path.join(output_dir, "html")
        os.makedirs(html_dir, exist_ok=True)

        # Optional: get driving polylines from distance provider
        distance_provider = kwargs.get("distance_provider")

        print(f"\n[Map] Generating maps for {result.total_days} days...")
        paths = []
        for dp in result.days:
            html_path = os.path.join(html_dir, f"day_{dp.day}.html")
            self._create_map(dp, html_path, img_w, img_h,
                             distance_provider, folium, DivIcon)

            if output_format == "png":
                img_dir = os.path.join(output_dir, "images")
                os.makedirs(img_dir, exist_ok=True)
                png_path = os.path.join(img_dir, f"day_{dp.day}.png")
                self._screenshot(html_path, png_path, img_w, img_h)
                paths.append(png_path)
            else:
                paths.append(html_path)

            print(f"  Day {dp.day} [{dp.point_count} pts] done")

        print(f"[Map] Complete: {html_dir}")
        return html_dir

    def _create_map(self, dp, html_path, img_w, img_h,
                    distance_provider, folium, DivIcon):
        points = dp.points
        coords = [p.coord for p in points]

        # Get driving route polylines if provider available
        route_pts = []
        if distance_provider and len(points) >= 2:
            for i in range(len(points) - 1):
                seg = distance_provider.get_polyline(points[i], points[i + 1])
                route_pts.extend(seg)

        avg_lat = sum(c[0] for c in coords) / len(coords)
        avg_lng = sum(c[1] for c in coords) / len(coords)
        zoom = self._calc_zoom(coords, img_w, img_h)

        m = folium.Map(
            location=[avg_lat, avg_lng], zoom_start=zoom,
            tiles="https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=2&style=8&x={x}&y={y}&z={z}",
            attr="Amap", width="100%", height="100%",
        )

        if route_pts:
            folium.PolyLine(route_pts, weight=5, color="#0066FF",
                            opacity=0.8).add_to(m)

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
                icon=DivIcon(icon_size=(28, 28), icon_anchor=(14, 14),
                             html=icon_html),
            ).add_to(m)

            # Short label
            display_name = pt.name
            if len(display_name) > 20:
                display_name = display_name[-20:]
            label_html = (
                f'<div style="background:rgba(255,255,255,.92);border:1px solid #666;'
                f'border-radius:3px;padding:2px 6px;font-size:12px;font-weight:bold;'
                f'color:#333;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.3)">'
                f'{num}.{display_name}</div>'
            )
            folium.Marker(
                location=[coord[0], coord[1]],
                icon=DivIcon(icon_size=(200, 24), icon_anchor=(-18, 12),
                             html=label_html),
            ).add_to(m)

        m.save(html_path)

        # Inject fullscreen CSS
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        css = ("<style>html,body{margin:0;padding:0;width:100%;height:100%;"
               "overflow:hidden}.folium-map{position:absolute;top:0;left:0;"
               "right:0;bottom:0}</style>")
        html = html.replace("</head>", css + "</head>")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

    @staticmethod
    def _calc_zoom(coords, img_w=1200, img_h=800):
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        lat_range = (max(lats) - min(lats)) * 1.4 or 0.005
        lng_range = (max(lngs) - min(lngs)) * 1.4 or 0.005
        for z in range(18, 5, -1):
            deg_per_px = 360 / (256 * 2 ** z)
            if lng_range / deg_per_px < img_w and lat_range / deg_per_px < img_h:
                return z
        return 6

    @staticmethod
    def _screenshot(html_path: str, png_path: str, width: int, height: int):
        cmd = [
            "chromium", "--headless", "--no-sandbox",
            "--disable-gpu", "--disable-software-rasterizer",
            f"--screenshot={png_path}", f"--window-size={width},{height}",
            "--virtual-time-budget=5000", f"file://{html_path}",
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
