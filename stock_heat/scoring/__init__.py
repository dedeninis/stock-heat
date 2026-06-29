"""溫度計算層（docs/04 §5–6）。"""

from .config import ScoringConfig, load_scoring_config
from .heat import MentionSignal, TickerHeat, compute_heat_scores, decay
from .velocity import annotate_velocity, heat_velocity, is_surge, surge_threshold

__all__ = [
    "ScoringConfig",
    "load_scoring_config",
    "MentionSignal",
    "TickerHeat",
    "compute_heat_scores",
    "decay",
    "heat_velocity",
    "is_surge",
    "surge_threshold",
    "annotate_velocity",
]
