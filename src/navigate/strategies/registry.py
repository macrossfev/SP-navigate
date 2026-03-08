"""Strategy registry for dynamic lookup."""
from __future__ import annotations

from typing import Dict, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseStrategy

STRATEGIES: Dict[str, Type["BaseStrategy"]] = {}


def register(name: str):
    """Decorator to register a strategy class."""
    def decorator(cls):
        STRATEGIES[name] = cls
        return cls
    return decorator
