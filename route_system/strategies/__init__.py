from .tsp import TspStrategy
from .cluster import ClusterStrategy

STRATEGIES = {
    "tsp": TspStrategy,
    "cluster": ClusterStrategy,
}
