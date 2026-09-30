from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any
import copy
import itertools
import pandas as pd

from models.domain import WorkSite, MachinePool, PlannerPolicy
from services.speed_service import speed_stage
from services.shadow_service import Shadow, shadow_fraction
from services.ea_service import train_ea
from services.capacity_service import capacity_screen


@dataclass
class ADPConfig:
    lookahead_days: int = 5
    beam_width: int = 8
    discount: float = 0.97
    max_action_works: int = 8
    deadline_weight: float = 20.0
    ea_tiebreak_weight: float = 0.003
    block_tiebreak_weight: float = 0.002
    freight_tiebreak_weight: float = 1.5
    shadow_credit_weight: float = 0.01


def _complete(state: Dict[str,dict]) -> bool:
    return all(s["complete"] for s in state.values())


def _machine_feasible(selected: List[WorkSite], pool: MachinePool) -> bool:
    used={}
    for w in selected:
        for m,n in w.machine_requirements.items():
            used[m]=used.get(m,0)+n
    return all(used.get(m,0)<=pool.quantities.get(m,0) for m in used)


def _demand(daily: pd.DataFrame, day:int) -> pd.Series:
    x=daily.loc[daily.day.eq(day)]
    return x.iloc[0] if not x.empty else daily.iloc[-1]


def _eligible(works: List[WorkSite], state: Dict[str,dict], day:int, max_n:int) -> List[WorkSite]:
    cand=[w for w in works if not state[w.work_id]["complete"] and w.earliest_day<=day]
    def key(w):
        st=state[w.work_id]
        rem=max(0.0,w.length_km-st["progress"])/max(w.base_productivity_km_per_block,1e-9)
        slack=w.latest_day-day-rem
        active=1 if (w.continuous and st["started"]) else 0
        return (-active,slack,w.priority,rem)
    return sorted(cand,key=key)[:max_n]


def _actions(eligible:List[WorkSite], state:Dict[str,dict], allow_pair:bool) -> List[Tuple[str,...]]:
    ids=[w.work_id for w in eligible]
    out=[()] + [(i,) for i in ids]
    if allow_pair:
        out += list(itertools.combinations(ids,2))
    active=[w.work_id for w in eligible if w.continuous and state[w.work_id]["started"] and not state[w.work_id]["complete"]]
    if active:
        retained=[a for a in out if all(i in a for i in active)]
        if retained:
            out=retained
    return out


def _shadow(selected:List[WorkSite], policy:PlannerPolicy) -> tuple[float,float,float]:
    physical=sum(w.block_minutes for w in selected)
    if len(selected)!=2 or not policy.allow_shadow_parallelism:
        return float(physical),0.0,0.0
    w1,w2=selected
    s1=Shadow(w1.work_id,w1.from_km,w1.to_km,0,w1.block_minutes)
    distance=abs((w2.from_km+w2.to_km)/2-(w1.from_km+w1.to_km)/2)
    # SYNTHETIC PLACEHOLDER: shadow propagated at representative 75 km/h.
    shift=60*distance/75.0
    s2=Shadow(w2.work_id,w2.from_km,w2.to_km,shift,shift+w2.block_minutes)
    phi=shadow_fraction(w2.block_minutes,s1,s2)
    credit=phi*min(w1.block_minutes,w2.block_minutes)
    footprint=max(w1.block_minutes,w2.block_minutes)+(1-phi)*min(w1.block_minutes,w2.block_minutes)
    return float(footprint),float(credit),float(phi)


def _advance(state:Dict[str,dict], selected:List[WorkSite], day:int):
    ns=copy.deepcopy(state); projected=[]
    for w in selected:
        st=ns[w.work_id]
        remaining=max(0.0,w.length_km-st["progress"])
        advance=min(remaining,w.base_productivity_km_per_block)
        start=min(w.from_km,w.to_km)+st["progress"]
        st["started"]=True
        st["progress"]+=advance
        if st["progress"]>=w.length_km-1e-9:
            st["progress"]=w.length_km
            st["complete"]=True
            st["completion_day"]=day
        projected.append((w,advance,start,start+advance))
    return ns,projected


def _restrictions(works:List[WorkSite], state:Dict[str,dict]) -> List[dict]:
    out=[]
    for w in works:
        st=state[w.work_id]
        if not st["started"] or st["complete"]:
            continue
        ratio=st["progress"]/max(w.length_km,1e-9)
        caution=speed_stage(ratio,w.work_type,w.psr_kph)
        # SYNTHETIC PLACEHOLDER: restricted length approximates the developed work front.
        length=max(0.05,min(w.length_km,max(w.base_productivity_km_per_block,st["progress"])))
        out.append({"section":w.section,"direction":w.direction,"length_km":length,
                    "psr_kph":w.psr_kph,"caution_kph":caution})
    return out


def _terminal_value(works,state,day,config,pool):
    rem=[]; deadline=0.0; loads={}
    for w in works:
        st=state[w.work_id]
        if st["complete"]:
            continue
        blocks=max(0.0,w.length_km-st["progress"])/max(w.base_productivity_km_per_block,1e-9)
        rem.append(blocks)
        deadline += max(0.0,day+blocks-w.latest_day)
        for m,n in w.machine_requirements.items():
            loads[m]=loads.get(m,0.0)+blocks*n
    if not rem:
        return 0.0
    resource_lb=max([loads[m]/max(1,pool.quantities.get(m,0)) for m in loads] or [0.0])
    return max(max(rem),resource_lb)+config.deadline_weight*deadline


def _evaluate(works,state,action,day,timetable,daily,pool,policy,config,work_by):
    selected=[work_by[i] for i in action]
    if not _machine_feasible(selected,pool):
        return None
    footprint,shadow_credit,phi=_shadow(selected,policy)
    if footprint>policy.max_block_minutes_per_day+1e-9:
        return None
    ns,projected=_advance(state,selected,day)
    ea=train_ea(timetable,_restrictions(works,ns))
    weighted=float(ea.weighted_ea_min.sum()) if len(ea) else 0.0
    if weighted>policy.max_weighted_ea_min_per_day+1e-9:
        return None
    cap=capacity_screen(_demand(daily,day),timetable,footprint,ea)
    if cap["goods_paths_accepted"]<policy.min_goods_paths_per_day:
        return None

    unfinished=sum(1 for s in ns.values() if not s["complete"])
    completion_cost=(1.0 if unfinished else 0.0) if policy.objective=="min_makespan" else float(unfinished)
    deadline=0.0
    for w in works:
        st=ns[w.work_id]
        if not st["complete"]:
            blocks=max(0.0,w.length_km-st["progress"])/max(w.base_productivity_km_per_block,1e-9)
            deadline += max(0.0,day+blocks-w.latest_day)

    immediate=(10.0*completion_cost + config.deadline_weight*deadline
               +config.ea_tiebreak_weight*weighted
               +config.block_tiebreak_weight*footprint
               +config.freight_tiebreak_weight*cap["unmet_goods"]
               -config.shadow_credit_weight*shadow_credit)
    return {"next_state":ns,"selected":selected,"projected":projected,"ea":ea,"cap":cap,
            "footprint":footprint,"shadow_credit":shadow_credit,"shadow_fraction":phi,
            "weighted_ea":weighted,"immediate_cost":immediate}


def _choose(works,state,day,timetable,daily,pool,policy,config,horizon):
    work_by={w.work_id:w for w in works}
    beam=[(0.0,state,day,None,[])]
    expanded=0; root_count=0
    depth_limit=min(config.lookahead_days,max(1,horizon-day))
    for depth in range(depth_limit):
        nxt=[]
        for cum,st,d,first,path in beam:
            if _complete(st):
                nxt.append((cum,st,d,first,path)); continue
            eligible=_eligible(works,st,d,config.max_action_works)
            acts=_actions(eligible,st,policy.allow_shadow_parallelism)
            if depth==0:
                root_count=len(acts)
            for action in acts:
                ev=_evaluate(works,st,action,d,timetable,daily,pool,policy,config,work_by)
                expanded+=1
                if ev is None:
                    continue
                fe=ev if first is None else first
                nc=cum+(config.discount**depth)*ev["immediate_cost"]
                nxt.append((nc,ev["next_state"],d+1,fe,path+[action]))
        if not nxt:
            break
        nxt.sort(key=lambda x:x[0]+(config.discount**(depth+1))*_terminal_value(works,x[1],x[2],config,pool))
        beam=nxt[:max(1,config.beam_width)]
    if not beam:
        return None,{"candidate_count":root_count,"expanded_nodes":expanded,"lookahead_days":depth_limit}
    scored=[]
    for cum,st,d,first,path in beam:
        total=cum+(config.discount**len(path))*_terminal_value(works,st,d,config,pool)
        scored.append((total,first,path))
    scored.sort(key=lambda x:x[0])
    total,best,path=scored[0]
    return best,{"candidate_count":root_count,"expanded_nodes":expanded,"lookahead_days":depth_limit,
                 "adp_value":total,"chosen_path":" -> ".join(["+".join(a) if a else "NO BLOCK" for a in path])}


def plan_adp(works:List[WorkSite], timetable:pd.DataFrame, daily_demand:pd.DataFrame,
             machine_pool:MachinePool, policy:PlannerPolicy, horizon_days:int=90,
             config:ADPConfig|None=None):
    config=config or ADPConfig()
    state={w.work_id:{"progress":0.0,"complete":False,"started":False,"completion_day":None} for w in works}
    schedule=[]; ea_rows=[]; audit=[]

    for day in range(horizon_days):
        if _complete(state):
            break
        best,diag=_choose(works,state,day,timetable,daily_demand,machine_pool,policy,config,horizon_days)
        if best is None:
            audit.append({"day":day,"status":"No feasible action under hard EA/capacity constraints",**diag})
            continue
        state=best["next_state"]
        label=" + ".join(w.work_id for w in best["selected"]) if best["selected"] else "NO BLOCK"
        for w,advance,start,end in best["projected"]:
            st=state[w.work_id]
            schedule.append({"day":day,"work_id":w.work_id,"work_type":w.work_type,"section":w.section,
                             "from_km":round(start,3),"to_km":round(end,3),"advance_km":round(advance,3),
                             "progress_km":round(st["progress"],3),"length_km":round(w.length_km,3),
                             "block_minutes":w.block_minutes,
                             "caution_kph":speed_stage(st["progress"]/max(w.length_km,1e-9),w.work_type,w.psr_kph),
                             "network_block_footprint_min":round(best["footprint"],2),
                             "shadow_credit_min":round(best["shadow_credit"],2),
                             "shadow_fraction":round(best["shadow_fraction"],3),
                             "weighted_ea_min":round(best["weighted_ea"],3),
                             "goods_paths_accepted":best["cap"]["goods_paths_accepted"],
                             "goods_demand":best["cap"]["goods_demand"],"unmet_goods":best["cap"]["unmet_goods"],
                             "adp_estimated_value":round(diag.get("adp_value",0.0),3),"synthetic_inputs":True})
        if len(best["ea"]):
            tmp=best["ea"].copy(); tmp["day"]=day; tmp["works"]=label
            ea_rows.extend(tmp.to_dict("records"))
        audit.append({"day":day,"status":"Allocated: "+label,"immediate_cost":round(best["immediate_cost"],3),
                      "weighted_ea_min":round(best["weighted_ea"],3),
                      "network_block_footprint_min":round(best["footprint"],2),
                      "shadow_credit_min":round(best["shadow_credit"],2),
                      "goods_paths_accepted":best["cap"]["goods_paths_accepted"],**diag})

    status=[]
    for w in works:
        st=state[w.work_id]
        pct=100*st["progress"]/max(w.length_km,1e-9)
        status.append({"work_id":w.work_id,"work_type":w.work_type,"priority":w.priority,
                       "progress_km":round(st["progress"],3),"length_km":round(w.length_km,3),
                       "progress_pct":round(min(100,pct),1),"complete":st["complete"],
                       "completion_day":st["completion_day"],"latest_day":w.latest_day,"synthetic":w.synthetic})
    return pd.DataFrame(schedule),pd.DataFrame(ea_rows),pd.DataFrame(status),pd.DataFrame(audit)
