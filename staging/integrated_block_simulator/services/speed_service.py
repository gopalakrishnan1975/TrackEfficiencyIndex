from typing import Dict

def speed_stage(progress_ratio: float, work_type: str, psr_kph: float) -> float:
    """Synthetic placeholder restoration rule. Replace with authorised work-specific rules."""
    if progress_ratio <= 0: return psr_kph
    if progress_ratio < 0.35: return min(40.0, psr_kph)
    if progress_ratio < 0.65: return min(75.0, psr_kph)
    if progress_ratio < 0.90: return min(110.0, psr_kph)
    return psr_kph

def effective_speed(base_speed: float, active_restrictions: Dict[str,float]) -> float:
    vals=[base_speed]+[v for v in active_restrictions.values() if v>0]
    return min(vals)
