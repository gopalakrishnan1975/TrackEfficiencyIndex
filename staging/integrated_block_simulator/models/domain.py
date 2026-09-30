from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class WorkSite:
    work_id: str
    work_type: str
    section: str
    direction: str
    from_km: float
    to_km: float
    priority: int
    earliest_day: int
    latest_day: int
    psr_kph: float
    base_productivity_km_per_block: float
    block_minutes: int
    continuous: bool
    machine_requirements: Dict[str, int] = field(default_factory=dict)
    speed_stages: List[float] = field(default_factory=lambda: [40, 75, 110, 130])
    synthetic: bool = True

    @property
    def length_km(self) -> float:
        return max(0.0, abs(self.to_km - self.from_km))

@dataclass
class MachinePool:
    quantities: Dict[str, int]

@dataclass
class PlannerPolicy:
    max_weighted_ea_min_per_day: float = 250.0
    min_goods_paths_per_day: int = 20
    max_passenger_cancellations_per_day: int = 0
    max_block_minutes_per_day: int = 240
    allow_shadow_parallelism: bool = True
    objective: str = "min_makespan"
