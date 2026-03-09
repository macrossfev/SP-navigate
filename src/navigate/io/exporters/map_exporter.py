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

        html_dir = os.path.join(output_dir, "html")
        img_dir = os.path.join(output_dir, "images")
        os.makedirs(html_dir, exist_ok=True)
        os.makedirs(img_dir, exist_ok=True)

        # Optional: get driving polylines from distance provider
        distance_provider = kwargs.get("distance_provider")

        print(f"\n[Map] Generating maps for {result.total_days} days...")
        paths = []
        for dp in result.days:
            html_path = os.path.join(html_dir, f"day_{dp.day}.html")
            png_path = os.path.join(img_dir, f"day_{dp.day}.png")

            self._create_map(dp, html_path, img_w, img_h,
                             distance_provider, folium, DivIcon)

            # Ensure image directory exists before screenshot
            os.makedirs(os.path.dirname(png_path), exist_ok=True)
            
            # Generate PNG screenshot
            self._screenshot(html_path, png_path, img_w, img_h)

            paths.append(html_path)
            print(f"  Day {dp.day} [{dp.point_count} pts] done")

        print(f"[Map] Complete: HTML maps in {html_dir}, PNG images in {img_dir}")
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

        # Add start point marker (company or hotel)
        if dp.start_point_name:
            start_icon = self._create_start_icon(folium, DivIcon, dp.start_point_name, dp.is_overnight)
            if dp.is_overnight and dp.hotel:
                start_coord = (dp.hotel.lat, dp.hotel.lng)
            else:
                start_coord = coords[0] if coords else (avg_lat, avg_lng)
            folium.Marker(
                location=start_coord,
                icon=start_icon,
                tooltip=dp.start_point_name,
            ).add_to(m)

        # Add sampling point markers
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

            # Short label with Chinese font support
            display_name = pt.name
            if len(display_name) > 20:
                display_name = display_name[-20:]
            label_html = (
                f'<div style="background:rgba(255,255,255,.92);border:1px solid #666;'
                f'border-radius:3px;padding:2px 6px;font-size:12px;font-weight:bold;'
                f'color:#333;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.3);'
                f'font-family:\'Noto Sans CJK SC\',\'Source Han Sans SC\',\'Microsoft YaHei\',sans-serif;">'
                f'{num}.{display_name}</div>'
            )
            folium.Marker(
                location=[coord[0], coord[1]],
                icon=DivIcon(icon_size=(200, 24), icon_anchor=(-18, 12),
                             html=label_html),
            ).add_to(m)

        # Add hotel marker for overnight trips
        if dp.is_overnight and dp.hotel:
            hotel_icon = self._create_hotel_icon(folium, DivIcon)
            folium.Marker(
                location=[dp.hotel.lat, dp.hotel.lng],
                icon=hotel_icon,
                tooltip=f"🏨 {dp.hotel.name}",
                popup=f"<b>住宿点</b><br>{dp.hotel.name}<br>靠近：{dp.hotel.near_point_id or 'N/A'}",
            ).add_to(m)

        # Add end point marker
        if dp.end_point_name and dp.end_point_name != dp.start_point_name:
            end_icon = self._create_end_icon(folium, DivIcon, dp.end_point_name)
            end_coord = coords[-1] if coords else (avg_lat, avg_lng)
            folium.Marker(
                location=end_coord,
                icon=end_icon,
                tooltip=dp.end_point_name,
            ).add_to(m)

        m.save(html_path)

        # Inject fullscreen CSS and Chinese font support
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        
        # Add Google Fonts for Chinese characters
        font_css = (
            '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700&display=swap" rel="stylesheet">'
        )
        
        css = (
            "<style>html,body{margin:0;padding:0;width:100%;height:100%;"
            "overflow:hidden}.folium-map{position:absolute;top:0;left:0;"
            "right:0;bottom:0}*{font-family:'Noto Sans SC','Noto Sans CJK SC',"
            "'Source Han Sans SC','Microsoft YaHei',sans-serif !important}</style>"
        )
        
        html = html.replace("</head>", font_css + css + "</head>")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

    @staticmethod
    def _create_start_icon(folium, DivIcon, name: str, is_overnight: bool):
        """Create start point marker icon."""
        color = "#FF6600" if is_overnight else "#00AA00"
        label = "🏨起点" if is_overnight else "🚗起点"
        icon_html = (
            f'<div style="background:{color};color:#fff;border-radius:50%;'
            f'width:32px;height:32px;display:flex;align-items:center;'
            f'justify-content:center;font-size:16px;font-weight:bold;'
            f'border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.5)">'
            f'{label}</div>'
        )
        return DivIcon(icon_size=(32, 32), icon_anchor=(16, 16), html=icon_html)

    @staticmethod
    def _create_end_icon(folium, DivIcon, name: str):
        """Create end point marker icon."""
        icon_html = (
            f'<div style="background:#CC0000;color:#fff;border-radius:50%;'
            f'width:32px;height:32px;display:flex;align-items:center;'
            f'justify-content:center;font-size:16px;font-weight:bold;'
            f'border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.5)">'
            f'🏁</div>'
        )
        return DivIcon(icon_size=(32, 32), icon_anchor=(16, 16), html=icon_html)

    @staticmethod
    def _create_hotel_icon(folium, DivIcon):
        """Create hotel marker icon."""
        icon_html = (
            f'<div style="background:#9933CC;color:#fff;border-radius:50%;'
            f'width:36px;height:36px;display:flex;align-items:center;'
            f'justify-content:center;font-size:20px;font-weight:bold;'
            f'border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.5)">'
            f'🏨</div>'
        )
        return DivIcon(icon_size=(36, 36), icon_anchor=(18, 18), html=icon_html)

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
        """Take screenshot using Playwright (recommended) or Chromium."""
        import os

        # Ensure output directory exists
        os.makedirs(os.path.dirname(png_path), exist_ok=True)

        try:
            # Try Playwright first (most reliable)
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_viewport_size({"width": width, "height": height})
                page.goto(f"file://{html_path}", wait_until="networkidle")
                page.screenshot(path=png_path, full_page=False)
                browser.close()
            
            if os.path.exists(png_path) and os.path.getsize(png_path) > 0:
                print(f"  ✓ Screenshot saved (Playwright): {png_path} ({os.path.getsize(png_path)} bytes)")
                return True
            else:
                print(f"  ⚠ Playwright screenshot empty")
                return False
                
        except ImportError:
            print(f"  ⚠ Playwright not available, trying Chromium...")
        except Exception as e:
            print(f"  ⚠ Playwright failed: {e}, trying Chromium...")
        
        # Fallback to Chromium (may fail on some systems)
        try:
            import subprocess
            
            chromium_paths = [
                "chromium",
                "chromium-browser", 
                "/snap/bin/chromium",
                "google-chrome",
                "google-chrome-stable",
            ]

            chromium_cmd = None
            for cmd in chromium_paths:
                try:
                    subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
                    chromium_cmd = cmd
                    break
                except:
                    continue

            if not chromium_cmd:
                print(f"  ⚠ No Chromium found")
                return False

            cmd = [
                chromium_cmd, "--headless", "--no-sandbox",
                f"--screenshot={png_path}", f"--window-size={width},{height}",
                "--virtual-time-budget=5000", f"file://{html_path}",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if os.path.exists(png_path) and os.path.getsize(png_path) > 0:
                print(f"  ✓ Screenshot saved (Chromium): {png_path} ({os.path.getsize(png_path)} bytes)")
                return True
            else:
                print(f"  ⚠ Chromium screenshot failed")
                return False
                
        except Exception as e:
            print(f"  ⚠ Screenshot error: {e}")
            return False
