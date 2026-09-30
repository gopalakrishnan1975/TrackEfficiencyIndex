from dataclasses import dataclass

@dataclass
class Shadow:
    work_id: str
    from_km: float
    to_km: float
    start_min: float
    end_min: float

def project_shadow(work_id:str, from_km:float, to_km:float, start_min:float, end_min:float,
                   reference_km:float, speed_kph:float) -> Shadow:
    """Projects the block envelope through a simple constant-speed time-space staircase.
    Placeholder: production model should use sectional PSR/TSR/stations/train class trajectories.
    """
    speed=max(speed_kph,1.0)
    anchor=(from_km+to_km)/2.0
    travel=60.0*abs(reference_km-anchor)/speed
    return Shadow(work_id,from_km,to_km,start_min+travel,end_min+travel)

def temporal_overlap_minutes(a: Shadow, b: Shadow) -> float:
    return max(0.0, min(a.end_min,b.end_min)-max(a.start_min,b.start_min))

def shadow_fraction(target_block_minutes: float, source: Shadow, target: Shadow) -> float:
    if target_block_minutes<=0: return 0.0
    return min(1.0, temporal_overlap_minutes(source,target)/target_block_minutes)
