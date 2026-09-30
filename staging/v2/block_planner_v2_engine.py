from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date, timedelta, datetime
from typing import List, Dict, Optional, Tuple
import math
import pandas as pd

# Planning defaults are placeholders and must be calibrated with field outputs / manuals.
WORK_CATALOG: Dict[str, Dict] = {
    "BCM-Plain Track": {"family":"BCM", "unit":"km", "rate_km_per_block":0.40, "default_block_h":3.0, "caution_kph":30, "continuous":True, "machine":"BCM"},
    "BCM-Point Machine": {"family":"BCM", "unit":"site", "rate_km_per_block":0.10, "default_block_h":4.0, "caution_kph":30, "continuous":True, "machine":"BCM"},
    "CTR/Primary-PQRS": {"family":"CTR", "unit":"km", "rate_km_per_block":0.45, "default_block_h":4.0, "caution_kph":30, "continuous":True, "machine":"PQRS"},
    "CTR/Primary-TRT": {"family":"CTR", "unit":"km", "rate_km_per_block":0.60, "default_block_h":4.0, "caution_kph":30, "continuous":True, "machine":"TRT"},
    "TRR": {"family":"TRR", "unit":"km", "rate_km_per_block":0.75, "default_block_h":3.0, "caution_kph":50, "continuous":True, "machine":"TRR"},
    "Through Tamping": {"family":"Tamping", "unit":"km", "rate_km_per_block":1.50, "default_block_h":2.5, "caution_kph":75, "continuous":False, "machine":"DUOMATIC"},
    "Crossovers": {"family":"XOVER", "unit":"site", "rate_km_per_block":0.10, "default_block_h":4.0, "caution_kph":30, "continuous":True, "machine":"XOVER_GANG"},
}

@dataclass
class WorkItem:
    work_id: str
    work_type: str
    section: str
    from_km: float
    to_km: float
    priority: int = 3  # 1 highest
    earliest_start: Optional[date] = None
    latest_finish: Optional[date] = None
    psr_kph: float = 100.0
    direction: str = "UP"
    block_hours: Optional[float] = None
    caution_kph: Optional[float] = None
    rate_km_per_block: Optional[float] = None
    continuous: Optional[bool] = None

    def normalized(self) -> Dict:
        if self.work_type not in WORK_CATALOG:
            raise ValueError(f"Unsupported work type: {self.work_type}")
        d = dict(WORK_CATALOG[self.work_type])
        d.update(asdict(self))
        d["length_km"] = max(0.0, abs(self.to_km - self.from_km))
        d["block_hours"] = self.block_hours or d["default_block_h"]
        d["caution_kph"] = self.caution_kph or d["caution_kph"]
        d["rate_km_per_block"] = self.rate_km_per_block or d["rate_km_per_block"]
        d["continuous"] = d["continuous"] if self.continuous is None else self.continuous
        return d


def _as_date(x) -> Optional[date]:
    if x is None or x == "" or (isinstance(x, float) and math.isnan(x)):
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    return pd.to_datetime(x).date()


def normalize_work_df(df: pd.DataFrame) -> List[Dict]:
    required = ["work_id","work_type","section","from_km","to_km","priority","psr_kph"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing work columns: {missing}")
    out=[]
    for _, r in df.iterrows():
        w=WorkItem(
            work_id=str(r.work_id), work_type=str(r.work_type), section=str(r.section),
            from_km=float(r.from_km), to_km=float(r.to_km), priority=int(r.priority),
            earliest_start=_as_date(r.get("earliest_start")), latest_finish=_as_date(r.get("latest_finish")),
            psr_kph=float(r.psr_kph), direction=str(r.get("direction","UP")),
            block_hours=None if pd.isna(r.get("block_hours")) else float(r.get("block_hours")),
            caution_kph=None if pd.isna(r.get("caution_kph")) else float(r.get("caution_kph")),
            rate_km_per_block=None if pd.isna(r.get("rate_km_per_block")) else float(r.get("rate_km_per_block")),
            continuous=None if pd.isna(r.get("continuous")) else bool(r.get("continuous")),
        )
        out.append(w.normalized())
    return out


def train_ea_minutes(train: pd.Series, active_sites: List[Dict]) -> float:
    """Constant-speed restriction approximation, train-specific using timetable route overlap.
    Timetable columns: train_id, section, direction, enter_min, exit_min, max_speed_kph.
    """
    ea=0.0
    vmax=float(train.max_speed_kph)
    for s in active_sites:
        if str(train.section)!=str(s["section"]):
            continue
        if str(train.direction).upper() not in ("BOTH",str(s.get("direction","UP")).upper()):
            continue
        length=float(s.get("active_length_km",s.get("length_km",0.0)))
        if length<=0: continue
        base=min(vmax,float(s["psr_kph"]))
        restricted=min(base,float(s["caution_kph"]))
        if restricted < base:
            ea += 60.0*length*(1.0/restricted - 1.0/base)
    return ea


def estimate_goods_paths(timetable_day: pd.DataFrame, block_hours: float, ea_by_train: pd.DataFrame,
                         headway_min: float=6.0) -> Dict:
    """Screening estimate only: converts consumed block time + added running time to path loss.
    Prefer train-graph/event model for production use.
    """
    goods=timetable_day[timetable_day["train_class"].str.lower().eq("goods")].copy()
    if goods.empty:
        return {"baseline_goods_paths":0,"estimated_goods_paths":0,"goods_paths_lost":0}
    baseline=len(goods)
    goods_ea=ea_by_train[ea_by_train.train_id.isin(goods.train_id)]["ea_min"].sum()
    lost_time=block_hours*60.0 + goods_ea
    lost_paths=math.ceil(lost_time/max(headway_min,1.0))
    est=max(0, baseline-lost_paths)
    return {"baseline_goods_paths":baseline,"estimated_goods_paths":est,"goods_paths_lost":baseline-est}


def _urgency_key(w: Dict, day: date):
    late_days=99999 if not w["latest_finish"] else (w["latest_finish"]-day).days
    return (w["priority"], late_days, w["work_id"])


def schedule_works(work_df: pd.DataFrame, timetable_df: pd.DataFrame, start_date: date,
                   horizon_days: int=120, max_blocks_per_day: int=1,
                   default_headway_min: float=6.0) -> Tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """Greedy continuity-aware scheduler.

    Core policy: once a continuous work item starts, it remains the active workfront on each
    eligible planning day until its end km is reached. It can be delayed only by date eligibility
    or an explicit impossibility (e.g. no timetable date / resource collision in later versions).
    """
    works=normalize_work_df(work_df)
    state={w["work_id"]:{"progress_km":0.0,"started":False,"completed":False,"last_day":None} for w in works}
    schedule=[]; train_impacts=[]; active_continuous=None

    tt=timetable_df.copy()
    if "service_date" in tt.columns:
        tt["service_date"]=pd.to_datetime(tt["service_date"]).dt.date
    else:
        tt["service_date"]=None

    for di in range(horizon_days):
        day=start_date+timedelta(days=di)
        blocks_used=0
        candidates=[]
        for w in works:
            st=state[w["work_id"]]
            if st["completed"]: continue
            if w["earliest_start"] and day<w["earliest_start"]: continue
            candidates.append(w)

        if active_continuous and not state[active_continuous]["completed"]:
            selected=[w for w in candidates if w["work_id"]==active_continuous]
        else:
            selected=sorted(candidates,key=lambda w:_urgency_key(w,day))[:max_blocks_per_day]

        for w in selected:
            if blocks_used>=max_blocks_per_day: break
            st=state[w["work_id"]]
            if not st["started"]:
                st["started"]=True
                if w["continuous"]: active_continuous=w["work_id"]
            remaining=w["length_km"]-st["progress_km"]
            advance=min(remaining,w["rate_km_per_block"])
            start_km=min(w["from_km"],w["to_km"])+st["progress_km"]
            end_km=start_km+advance
            st["progress_km"]+=advance; st["last_day"]=day
            if st["progress_km"]>=w["length_km"]-1e-9:
                st["completed"]=True
                if active_continuous==w["work_id"]: active_continuous=None

            active_site={**w,"active_length_km":advance,"active_from_km":start_km,"active_to_km":end_km}
            day_tt=tt[(tt.service_date.isna()) | (tt.service_date==day)].copy()
            impacts=[]
            for _,tr in day_tt.iterrows():
                ea=train_ea_minutes(tr,[active_site])
                impacts.append({"date":day,"train_id":tr.train_id,"train_class":tr.train_class,
                                "section":tr.section,"ea_min":round(ea,3),"work_id":w["work_id"]})
            impact_df=pd.DataFrame(impacts)
            train_impacts.extend(impacts)
            cap=estimate_goods_paths(day_tt,w["block_hours"],impact_df,default_headway_min) if not day_tt.empty else {
                "baseline_goods_paths":0,"estimated_goods_paths":0,"goods_paths_lost":0}
            schedule.append({
                "date":day,"work_id":w["work_id"],"work_type":w["work_type"],"section":w["section"],
                "direction":w["direction"],"from_km":round(start_km,3),"to_km":round(end_km,3),
                "priority":w["priority"],"block_hours":w["block_hours"],"psr_kph":w["psr_kph"],
                "caution_kph":w["caution_kph"],"continuous":w["continuous"],
                "work_complete":st["completed"],"progress_km":round(st["progress_km"],3),
                "total_length_km":round(w["length_km"],3),
                "total_EA_min":round(sum(x["ea_min"] for x in impacts),3),**cap,
                "late_finish_breach":bool(w["latest_finish"] and day>w["latest_finish"] and not st["completed"])
            })
            blocks_used+=1

    status=[]
    for w in works:
        st=state[w["work_id"]]
        status.append({"work_id":w["work_id"],"work_type":w["work_type"],"section":w["section"],
                       "priority":w["priority"],"planned_length_km":w["length_km"],
                       "progress_km":round(st["progress_km"],3),"completed":st["completed"],
                       "latest_finish":w["latest_finish"],"last_work_day":st["last_day"]})
    return pd.DataFrame(schedule), pd.DataFrame(train_impacts), pd.DataFrame(status)