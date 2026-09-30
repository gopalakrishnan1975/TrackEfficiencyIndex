from __future__ import annotations
from typing import Dict, List, Tuple
import itertools
import math
import pandas as pd
from models.domain import WorkSite, MachinePool, PlannerPolicy
from services.speed_service import speed_stage
from services.shadow_service import Shadow, shadow_fraction
from services.ea_service import train_ea
from services.capacity_service import capacity_screen

def _machine_feasible(selected: List[WorkSite], pool: MachinePool) -> bool:
    used={}
    for w in selected:
        for m,n in w.machine_requirements.items(): used[m]=used.get(m,0)+n
    return all(used.get(m,0)<=pool.quantities.get(m,0) for m in used)

def _candidate_actions(active_ids: list[str], eligible: list[WorkSite], allow_pair: bool) -> list[tuple[str,...]]:
    ids=[w.work_id for w in eligible]
    acts=[()] + [(i,) for i in ids]
    if allow_pair:
        acts += [tuple(x) for x in itertools.combinations(ids,2)]
    if active_ids:
        acts=[a for a in acts if all(i in a for i in active_ids)] or [tuple(active_ids)]
    return acts

def plan(works: List[WorkSite], timetable: pd.DataFrame, daily_demand: pd.DataFrame,
         machine_pool: MachinePool, policy: PlannerPolicy, horizon_days:int=90) -> Tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    state={w.work_id:{"progress":0.0,"complete":False,"started":False,"completion_day":None} for w in works}
    work_by={w.work_id:w for w in works}
    schedule=[]; ea_rows=[]; diagnostics=[]

    for day in range(horizon_days):
        if all(s["complete"] for s in state.values()): break
        dd=daily_demand.loc[daily_demand.day.eq(day)]
        if dd.empty: dd=daily_demand.iloc[[-1]]
        dd=dd.iloc[0]
        eligible=[w for w in works if not state[w.work_id]["complete"] and w.earliest_day<=day<=max(w.latest_day,horizon_days)]
        active=[w.work_id for w in eligible if w.continuous and state[w.work_id]["started"] and not state[w.work_id]["complete"]]
        candidates=_candidate_actions(active,eligible,policy.allow_shadow_parallelism)
        best=None
        for action in candidates:
            selected=[work_by[i] for i in action]
            if not _machine_feasible(selected,machine_pool): continue
            if sum(w.block_minutes for w in selected)>policy.max_block_minutes_per_day and len(selected)<=1: continue
            restrictions=[]; block_capacity=sum(w.block_minutes for w in selected)
            shadow_credit=0.0
            if len(selected)==2 and policy.allow_shadow_parallelism:
                w1,w2=selected
                s1=Shadow(w1.work_id,w1.from_km,w1.to_km,0,w1.block_minutes)
                distance=abs((w2.from_km+w2.to_km)/2-(w1.from_km+w1.to_km)/2)
                shift=60*distance/75.0
                s2=Shadow(w2.work_id,w2.from_km,w2.to_km,shift,shift+w2.block_minutes)
                phi=shadow_fraction(w2.block_minutes,s1,s2)
                shadow_credit=phi*min(w1.block_minutes,w2.block_minutes)
                block_capacity=max(w1.block_minutes,w2.block_minutes)+(1-phi)*min(w1.block_minutes,w2.block_minutes)
            projected=[]
            for w in selected:
                st=state[w.work_id]
                remaining=w.length_km-st["progress"]
                advance=min(remaining,w.base_productivity_km_per_block)
                ratio=(st["progress"]+advance)/max(w.length_km,1e-9)
                caution=speed_stage(ratio,w.work_type,w.psr_kph)
                restrictions.append({"section":w.section,"direction":w.direction,"length_km":max(advance,0.05),"psr_kph":w.psr_kph,"caution_kph":caution})
                projected.append((w,advance,caution))
            ea=train_ea(timetable,restrictions)
            weighted=float(ea.weighted_ea_min.sum()) if len(ea) else 0.0
            if weighted>policy.max_weighted_ea_min_per_day: continue
            cap=capacity_screen(dd,timetable,block_capacity,ea)
            if cap["goods_paths_accepted"]<policy.min_goods_paths_per_day: continue
            progress_gain=sum(a for _,a,_ in projected)
            urgency=sum(max(0,day-w.latest_day+1) + 1/max(1,w.latest_day-day+1) for w,_,_ in projected)
            completion_bonus=sum(4.0 for w,a,_ in projected if state[w.work_id]["progress"]+a>=w.length_km-1e-9)
            score=12*progress_gain+2*urgency+completion_bonus+0.02*shadow_credit-0.015*weighted-0.8*cap["unmet_goods"]
            key=(score,-weighted,-cap["unmet_goods"])
            if best is None or key>best[0]: best=(key,selected,projected,ea,cap,block_capacity,shadow_credit)
        if best is None:
            diagnostics.append({"day":day,"status":"No feasible engineering allocation","synthetic":True})
            continue
        _,selected,projected,ea,cap,block_capacity,shadow_credit=best
        for w,advance,caution in projected:
            st=state[w.work_id]; st["started"]=True
            start=min(w.from_km,w.to_km)+st["progress"]
            st["progress"]+=advance
            if st["progress"]>=w.length_km-1e-9:
                st["complete"]=True; st["completion_day"]=day
            schedule.append({"day":day,"work_id":w.work_id,"work_type":w.work_type,"section":w.section,
                             "from_km":start,"to_km":start+advance,"advance_km":advance,
                             "progress_km":st["progress"],"length_km":w.length_km,
                             "block_minutes":w.block_minutes,"caution_kph":caution,
                             "network_block_footprint_min":block_capacity,"shadow_credit_min":shadow_credit,
                             "weighted_ea_min":float(ea.weighted_ea_min.sum()),
                             "goods_paths_accepted":cap["goods_paths_accepted"],"goods_demand":cap["goods_demand"],
                             "unmet_goods":cap["unmet_goods"],"synthetic_inputs":True})
        if len(ea):
            tmp=ea.copy(); tmp["day"]=day; tmp["works"]="+".join(w.work_id for w in selected); ea_rows.extend(tmp.to_dict("records"))
        diagnostics.append({"day":day,"status":"Allocated: "+",".join(w.work_id for w in selected) if selected else "No block",
                            "network_block_footprint_min":block_capacity,"shadow_credit_min":shadow_credit,
                            "weighted_ea_min":float(ea.weighted_ea_min.sum()) if len(ea) else 0,
                            "goods_paths_accepted":cap["goods_paths_accepted"],"synthetic":True})

    status=[]
    for w in works:
        st=state[w.work_id]
        status.append({"work_id":w.work_id,"work_type":w.work_type,"progress_km":st["progress"],"length_km":w.length_km,
                       "complete":st["complete"],"completion_day":st["completion_day"],"synthetic":w.synthetic})
    return pd.DataFrame(schedule),pd.DataFrame(ea_rows),pd.DataFrame(status)
