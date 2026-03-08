"""Route planning strategies."""
from .registry import STRATEGIES, register
from .base import BaseStrategy
# Import strategies to trigger registration
from . import tsp
from . import cluster

__all__ = ["STRATEGIES", "register", "BaseStrategy"]
