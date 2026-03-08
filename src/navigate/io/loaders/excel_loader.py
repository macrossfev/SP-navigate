"""Excel/CSV data loader with configurable column mapping."""
from __future__ import annotations

import os
from typing import Dict, List, Optional, TYPE_CHECKING

import pandas as pd

from navigate.core.models import Point
from .base import BaseLoader

if TYPE_CHECKING:
    from navigate.core.config import DataSourceConfig, ColumnMapping


class ExcelLoader(BaseLoader):
    """Load points from Excel (.xlsx/.xls) or CSV files."""

    def load(self, source: "DataSourceConfig") -> List[Point]:
        file_path = source.file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Data file not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext == ".xls":
            df = pd.read_excel(file_path, engine="xlrd")
        else:
            df = pd.read_excel(file_path, engine="openpyxl")

        if source.skip_rows > 0:
            df = df.iloc[source.skip_rows:].reset_index(drop=True)

        cm = source.column_mapping
        if cm is None:
            raise ValueError("column_mapping is required for loading points")

        points = []
        for idx, row in df.iterrows():
            # Get name
            name = str(row[cm.name]).strip() if cm.name in df.columns else ""
            if not name or name == "nan":
                continue

            # Get coordinates
            lng, lat = None, None
            if cm.coordinates and cm.coordinates in df.columns:
                coord_str = str(row[cm.coordinates]).strip()
                if coord_str and coord_str != "nan" and "," in coord_str:
                    parts = coord_str.split(",")
                    lng, lat = float(parts[0]), float(parts[1])
            elif cm.lng and cm.lat and cm.lng in df.columns and cm.lat in df.columns:
                lng_val = row[cm.lng]
                lat_val = row[cm.lat]
                if pd.notna(lng_val) and pd.notna(lat_val):
                    lng, lat = float(lng_val), float(lat_val)

            if lng is None or lat is None:
                continue

            # Get ID
            point_id = str(idx)
            if cm.id and cm.id in df.columns:
                point_id = str(row[cm.id]).strip()

            # Get metadata
            metadata = {}
            if cm.metadata:
                for meta_key, col_name in cm.metadata.items():
                    if col_name in df.columns:
                        val = row[col_name]
                        metadata[meta_key] = str(val).strip() if pd.notna(val) else ""

            points.append(Point(
                id=point_id,
                name=name,
                lng=lng,
                lat=lat,
                metadata=metadata,
            ))

        return points


class SurveyLoader:
    """Load supplementary survey data and match to existing points."""

    def load_and_match(self, source: "DataSourceConfig",
                       points: List[Point],
                       corrections: Optional["DataSourceConfig"] = None):
        """Load survey data and attach matching info to points as metadata."""
        if not source or not source.file or not os.path.exists(source.file):
            return

        ext = os.path.splitext(source.file)[1].lower()
        if ext == ".xls":
            df = pd.read_excel(source.file, engine="xlrd")
        else:
            df = pd.read_excel(source.file, engine="openpyxl")

        if source.skip_rows > 0:
            # Reassign columns from the header rows if needed
            if source.column_mapping and source.column_mapping.metadata:
                # Use the existing column names
                pass
            df = df.iloc[source.skip_rows:].reset_index(drop=True)

        # Build survey map keyed by match_key column
        match_key_col = source.match_key
        if not match_key_col or match_key_col not in df.columns:
            return

        cm = source.column_mapping
        survey_map: Dict[str, dict] = {}
        for _, row in df.iterrows():
            key = str(row[match_key_col]).strip() if pd.notna(row[match_key_col]) else ""
            if not key:
                continue
            entry = {}
            if cm and cm.metadata:
                for meta_key, col_name in cm.metadata.items():
                    if col_name in df.columns:
                        val = row[col_name]
                        entry[meta_key] = str(val).strip() if pd.notna(val) else ""
            survey_map[key] = entry

        # Load corrections map
        addr_to_orig: Dict[str, str] = {}
        if corrections and corrections.file and os.path.exists(corrections.file):
            addr_to_orig = self._load_corrections(corrections, source.strip_prefix)

        # Match survey data to points
        strip_prefix = source.strip_prefix
        is_fuzzy = source.match_mode == "fuzzy"
        matched = 0

        for pt in points:
            info = self._match(pt.name, survey_map, addr_to_orig,
                               strip_prefix, is_fuzzy)
            if info:
                matched += 1
                pt.metadata.update(info)

        print(f"  Survey matched: {matched}/{len(points)}")

    def _load_corrections(self, source: "DataSourceConfig",
                          strip_prefix: str) -> Dict[str, str]:
        ext = os.path.splitext(source.file)[1].lower()
        if ext == ".xls":
            df = pd.read_excel(source.file, engine="xlrd")
        else:
            df = pd.read_excel(source.file, engine="openpyxl")

        cm = source.column_mapping
        orig_col = cm.metadata.get("original", "\u539f\u59cb\u5730\u5740") if cm and cm.metadata else "\u539f\u59cb\u5730\u5740"
        corrected_col = cm.metadata.get("corrected") if cm and cm.metadata else None

        # If corrected column is -1 or not specified, use last column
        if corrected_col == "-1" or corrected_col is None:
            corrected_col = df.columns[-1]

        mapping = {}
        for _, row in df.iterrows():
            orig = str(row[orig_col]).replace(strip_prefix, "").strip() if pd.notna(row[orig_col]) else ""
            fix = row[corrected_col]
            if pd.notna(fix) and str(fix).strip():
                full_fix = str(fix).strip()
                mapping[full_fix] = orig
                if strip_prefix and not full_fix.startswith(strip_prefix[:2]):
                    mapping[f"{strip_prefix}{full_fix}"] = orig
        return mapping

    def _match(self, point_name: str, survey_map: dict,
               addr_to_orig: dict, strip_prefix: str,
               fuzzy: bool) -> Optional[dict]:
        short = point_name.replace(strip_prefix, "").strip() if strip_prefix else point_name

        # Exact match
        if short in survey_map:
            return survey_map[short]

        # Via correction table
        orig = addr_to_orig.get(point_name) or addr_to_orig.get(short)
        if orig and orig in survey_map:
            return survey_map[orig]

        if not fuzzy:
            return None

        # Fuzzy match
        def normalize(s):
            for ch in ".-\u00b7\u5c0f\u533a\uff08\uff09()":
                s = s.replace(ch, "")
            return s.strip()

        short_norm = normalize(short)
        for key, val in survey_map.items():
            key_norm = normalize(key)
            if key in short or short in key:
                return val
            if key_norm and short_norm and (key_norm in short_norm or short_norm in key_norm):
                return val
        return None
