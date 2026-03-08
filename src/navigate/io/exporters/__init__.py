"""Result exporters."""
from .base import BaseExporter
from .json_exporter import JsonExporter
from .excel_exporter import ExcelExporter
from .docx_exporter import DocxExporter
from .map_exporter import MapExporter

EXPORTERS = {
    "json": JsonExporter,
    "excel": ExcelExporter,
    "docx": DocxExporter,
    "map": MapExporter,
}

__all__ = ["BaseExporter", "JsonExporter", "ExcelExporter",
           "DocxExporter", "MapExporter", "EXPORTERS"]
