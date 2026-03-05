"""
数据加载与清洗模块
统一加载地址列表、坐标、二供调查表、地址修正表
"""
import pandas as pd
import math
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from .config import RouteConfig


@dataclass
class SamplingPoint:
    """采样点数据"""
    index: int              # 在列表中的序号
    name: str               # 完整地址
    short_name: str         # 简称（去掉"重庆市长寿区"）
    lng: float              # 经度 (GCJ-02)
    lat: float              # 纬度 (GCJ-02)
    # 二供调查信息
    community_name: str = ""
    property_company: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    households: str = ""
    population: str = ""
    equipment: str = ""
    management: str = ""


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间球面距离（km）"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def build_distance_matrix(points: List[SamplingPoint]) -> List[List[float]]:
    """构建对称距离矩阵（km）"""
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine(points[i].lat, points[i].lng,
                          points[j].lat, points[j].lng)
            dist[i][j] = d
            dist[j][i] = d
    return dist


class DataLoader:
    """数据加载与清洗"""

    def __init__(self, config: RouteConfig):
        self.config = config
        self._survey_map: Dict[str, dict] = {}
        self._addr_to_orig: Dict[str, str] = {}

    def load_all(self) -> List[SamplingPoint]:
        """加载所有数据，返回清洗后的采样点列表"""
        print("[数据加载] 读取地址列表...")
        points = self._load_addresses()
        print(f"  → {len(points)} 个有效点位")

        print("[数据加载] 读取二供调查表...")
        self._load_survey()
        print(f"  → {len(self._survey_map)} 条小区记录")

        print("[数据加载] 读取地址修正表...")
        self._load_fix_mapping()
        print(f"  → {len(self._addr_to_orig)} 条修正映射")

        print("[数据加载] 匹配调查信息...")
        matched = 0
        for pt in points:
            info = self._match_survey(pt.name)
            if info:
                matched += 1
                pt.community_name = info.get("community", "")
                pt.property_company = info.get("物业名称", "")
                pt.contact_person = info.get("联系人", "")
                pt.contact_phone = info.get("联系电话", "")
                pt.households = info.get("服务户数", "")
                pt.population = info.get("服务人口", "")
                pt.equipment = info.get("水箱类型", "")
                pt.management = info.get("管理方式", "")
        print(f"  → 匹配成功 {matched}/{len(points)}")

        return points

    def _load_addresses(self) -> List[SamplingPoint]:
        df = pd.read_excel(self.config.address_file, engine="openpyxl")
        points = []
        for idx, row in df.iterrows():
            addr = str(row["地址"]).strip()
            coord = str(row["坐标"]).strip()
            if not coord or coord == "nan":
                continue
            lng, lat = coord.split(",")
            short = addr.replace("重庆市长寿区", "").replace("重庆市", "")
            points.append(SamplingPoint(
                index=len(points),
                name=addr,
                short_name=short,
                lng=float(lng),
                lat=float(lat),
            ))
        return points

    def _load_survey(self):
        df = pd.read_excel(self.config.survey_file)
        df.columns = [
            "序号", "小区名称", "泵房数量", "加压设施数量",
            "服务户数", "服务人口", "物业名称", "联系人", "联系电话",
            "管理方式", "水箱类型", "采样1", "采样2", "采样3"
        ]
        df = df.iloc[2:].reset_index(drop=True)
        df = df[df["小区名称"].notna() & (df["小区名称"].str.strip() != "")]

        for _, row in df.iterrows():
            name = str(row["小区名称"]).strip()
            self._survey_map[name] = {
                "community": name,
                "物业名称": str(row["物业名称"]) if pd.notna(row["物业名称"]) else "",
                "联系人": str(row["联系人"]) if pd.notna(row["联系人"]) else "",
                "联系电话": str(row["联系电话"]) if pd.notna(row["联系电话"]) else "",
                "服务户数": str(row["服务户数"]) if pd.notna(row["服务户数"]) else "",
                "服务人口": str(row["服务人口"]) if pd.notna(row["服务人口"]) else "",
                "水箱类型": str(row["水箱类型"]) if pd.notna(row["水箱类型"]) else "",
                "管理方式": str(row["管理方式"]) if pd.notna(row["管理方式"]) else "",
            }

    def _load_fix_mapping(self):
        df = pd.read_excel(self.config.fix_address_file, engine="openpyxl")
        fix_col = df.columns[-1]
        for _, row in df.iterrows():
            orig = str(row["原始地址"]).replace("重庆市长寿区", "").strip()
            fix_addr = row[fix_col]
            if pd.notna(fix_addr) and str(fix_addr).strip():
                full_fix = str(fix_addr).strip()
                self._addr_to_orig[full_fix] = orig
                if not full_fix.startswith("重庆"):
                    self._addr_to_orig[f"重庆市长寿区{full_fix}"] = orig
                else:
                    self._addr_to_orig[full_fix] = orig

    def _match_survey(self, point_name: str) -> Optional[dict]:
        short = point_name.replace("重庆市长寿区", "").replace("重庆市", "").strip()

        # 精确匹配
        if short in self._survey_map:
            return self._survey_map[short]

        # 通过修正地址反查
        orig = self._addr_to_orig.get(point_name) or self._addr_to_orig.get(short)
        if orig and orig in self._survey_map:
            return self._survey_map[orig]

        # 模糊匹配
        def normalize(s):
            return s.replace(".", "").replace("·", "").replace("·", "").replace("小区", "").replace("（", "(").replace("）", ")").strip()

        short_norm = normalize(short)
        for key, val in self._survey_map.items():
            key_norm = normalize(key)
            if key in short or short in key:
                return val
            if key_norm and short_norm and (key_norm in short_norm or short_norm in key_norm):
                return val
        return None
