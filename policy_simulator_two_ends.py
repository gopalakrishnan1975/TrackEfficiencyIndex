"""Endpoint-aware, whole-patch synthetic maintenance simulation.
Each 400 m packet must fit in one possession; no partial work carry-over.
Not an IRPWM clearance authority or actual train-graph capacity model.
"""
from copy import deepcopy

DEFAULT = dict(section_km=12, patch_km=.4, coaching_trains=40, goods_trains=25,
    coach_speed_kph=130, goods_speed_kph=60, mps_kph=130, machine_transit_kph=40,
    headway_min=6, station_exit="nearest", dispatch_min=10, receive_min=10,
    setup_min=15, setup_retained_min=6, cutter_remove_from_track_min=10,
    cleanup_min=5, bcm_clean_min_per_patch=120, hobcm_clean_min_per_patch=73,
    duomatic_min_per_pass=35, dgs_min_per_pass=15,
    bcm_machines=2, duomatics=1, dgs_machines=1, retained_workspot_speed_kph=30,
    normal_workspot_speed_kph=40, retain_cutter_outside=False, block_hours=3,
    bcm_days_of_week=[0,1,2,3,4,5], restoration_days_of_week=[0,1,2,3,4,5],
    coach_EA_cap_min=None, horizon_days=120, daily_actions={})
STAGES = [("t1",1,1), ("t2",4,1), ("t3",7,2)]

def sched_time(tasks, kind, p, retained=False):
    """Simulated minutes for one machine's complete possession."""
    if not tasks:
        return 0.
    rear = max(x for x, _ in tasks)
    ahead = max(p["section_km"]-x for x, _ in tasks)
    mode = p["station_exit"]
    if mode not in ("rear", "ahead", "nearest"):
        raise ValueError("station_exit must be rear, ahead or nearest")
    far = rear if mode=="rear" else ahead if mode=="ahead" else min(rear,ahead)
    transit = 120*far / p["machine_transit_kph"]
    handling = 0
    if kind in ("BCM", "HOBCM"):
        handling = p["setup_retained_min"] if retained else p["setup_min"]
        handling += p["cutter_remove_from_track_min"] + p["cleanup_min"]
    return p["dispatch_min"] + p["receive_min"] + transit + handling + sum(duration for _,duration in tasks)

def speed(job, day, p):
    if job.get("t3") is not None and day-job["start"]>=9 and day>job["t3"]:
        return p["mps_kph"]
    if job.get("t3") is not None and day-job["start"]>=7:
        return min(110,p["mps_kph"])
    if job.get("t2") is not None and day-job["start"]>=5 and day>job["t2"]:
        return min(75,p["mps_kph"])
    return p["retained_workspot_speed_kph"] if job["retained"] else p["normal_workspot_speed_kph"]

def metrics(jobs, day, block_min, p):
    speeds = [speed(job,day,p) for job in jobs]
    def ea(v):
        return sum(60*p["patch_km"]*(1/min(v,s)-1/v) for s in speeds)
    ec,eg=ea(p["coach_speed_kph"]),ea(p["goods_speed_kph"])
    n=p["coaching_trains"]+p["goods_trains"]
    coach_t=60*p["section_km"]/p["coach_speed_kph"]+ec
    goods_t=60*p["section_km"]/p["goods_speed_kph"]+eg
    mean_occ=(p["coaching_trains"]*(coach_t+p["headway_min"])+p["goods_trains"]*(goods_t+p["headway_min"]))/n
    fluid=(1440-block_min)/mean_occ
    return ec,eg,fluid,p["coaching_trains"]*ec+p["goods_trains"]*eg

def run(plan, label="simulation"):
    p={**DEFAULT,**deepcopy(plan)}
    n=round(p["section_km"]/p["patch_km"])
    if abs(n*p["patch_km"]-p["section_km"])>1e-7: raise ValueError("Section length must be in 400m multiples")
    if p["machine_transit_kph"]>40 or p["machine_transit_kph"]<=0: raise ValueError("BCM travel speed must be between 0 and 40 km/h")
    if p["duomatics"]<1 or p["dgs_machines"]<1: raise ValueError("At least one Duomatic and DGS required")
    kind="HOBCM" if p["bcm_machines"]==0 else "BCM"
    cleaner_count=1 if kind=="HOBCM" else p["bcm_machines"]
    jobs=[];rows=[];events=[]
    totals={"BCM":0.,"HOBCM":0.,"DUO":0.,"DGS":0.}
    rejected=0
    for day in range(int(p["horizon_days"])):
        overrides=p.get("daily_actions",{}).get(str(day+1),{})
        block_hours=overrides.get("block_hours",p["block_hours"])
        B=block_hours*60.
        bcm_allowed=overrides.get("allow_bcm",day%7 in p["bcm_days_of_week"])
        restore_allowed=overrides.get("allow_restoration",day%7 in p["restoration_days_of_week"])
        retained=overrides.get("retain_cutter_outside",p["retain_cutter_outside"])
        ops={kind:[[] for _ in range(cleaner_count)],"DUO":[[] for _ in range(p["duomatics"])],"DGS":[[] for _ in range(p["dgs_machines"])]}
        counts={kind:0,"DUO":0,"DGS":0}
        def choose(k,x,duration):
            possibilities=[(sched_time(tasks+[(x,duration)],k,p,retained),idx)
                           for idx,tasks in enumerate(ops[k])
                           if sched_time(tasks+[(x,duration)],k,p,retained)<=B+1e-7]
            return min(possibilities)[1] if possibilities else None
        def add(k,idx,x,duration):
            ops[k][idx].append((x,duration))
            counts[k]+=1
        if restore_allowed:
            for stage,min_age,dgs_passes in reversed(STAGES):
                for job in jobs:
                    if job[stage] is not None or day-job["start"]<min_age: continue
                    if stage=="t3" and job["t2"] is None: continue
                    if stage=="t2" and job["t1"] is None: continue
                    x=job["x"]
                    u=choose("DUO",x,p["duomatic_min_per_pass"])
                    g=choose("DGS",x,p["dgs_min_per_pass"]*dgs_passes)
                    if u is not None and g is not None:
                        add("DUO",u,x,p["duomatic_min_per_pass"])
                        add("DGS",g,x,p["dgs_min_per_pass"]*dgs_passes)
                        job[stage]=day
        if bcm_allowed:
            for machine in range(cleaner_count):
                if len(jobs)>=n: break
                x=(len(jobs)+.5)*p["patch_km"]
                duration=p["hobcm_clean_min_per_patch"] if kind=="HOBCM" else p["bcm_clean_min_per_patch"]
                a=choose(kind,x,duration)
                u=choose("DUO",x,p["duomatic_min_per_pass"])
                g=choose("DGS",x,p["dgs_min_per_pass"])
                if a is None or u is None or g is None: continue
                newjob=dict(x=x,start=day,retained=retained,t1=None,t2=None,t3=None)
                if p["coach_EA_cap_min"] is not None:
                    if metrics(jobs+[newjob],day,B,p)[0]>p["coach_EA_cap_min"]+1e-8:
                        rejected+=1
                        continue
                add(kind,a,x,duration)
                add("DUO",u,x,p["duomatic_min_per_pass"])
                add("DGS",g,x,p["dgs_min_per_pass"])
                jobs.append(newjob)
        haswork=any(tasks for machines in ops.values() for tasks in machines)
        actual_block=B if haswork else 0.
        ec,eg,paths,train_min=metrics(jobs,day,actual_block,p)
        row=dict(scenario=label,day=day+1,block_hours=actual_block/60,
            BCM_packets_today=counts[kind],DUO_packing_jobs=counts["DUO"],
            DGS_stabilisation_jobs=counts["DGS"],cleaned_km=len(jobs)*p["patch_km"],
            restored_130_km=sum(speed(j,day,p)>=p["mps_kph"] for j in jobs)*p["patch_km"],
            coaching_EA_min=ec,goods_EA_min=eg,train_minutes_lost=train_min,
            fluid_paths_proxy=paths,
            target_65_feasible_proxy=paths+1e-7>=p["coaching_trains"]+p["goods_trains"])
        for k in totals:
            occupied=sum(sched_time(tasks,k,p,retained) for tasks in ops.get(k,[]))
            totals[k]+=occupied
            row[k+"_machine_hours"]=round(occupied/60,3)
        rows.append(row)
        if len(jobs)==n and row["restored_130_km"]>=p["section_km"]-1e-8: break
    for idx,job in enumerate(jobs,1):
        for milestone in (75,110,p["mps_kph"]):
            found=next((day for day in range(job["start"],p["horizon_days"]) if speed(job,day,p)>=milestone),None)
            events.append(dict(scenario=label,patch=idx,position_km=round(job["x"],2),
                start_day=job["start"]+1,speed_kph=milestone,
                reach_day=found+1 if found is not None else "",
                elapsed_calendar_days=found-job["start"]+1 if found is not None else ""))
    summary=dict(scenario=label,completed=len(jobs)==n and rows[-1]["restored_130_km"]>=p["section_km"]-1e-8,
        finish_day=len(rows),cleaned_km=round(len(jobs)*p["patch_km"],2),
        restored_km=round(rows[-1]["restored_130_km"],2),
        total_block_h=round(sum(r["block_hours"] for r in rows),2),
        BCM_or_HOBCM_machine_h=round((totals["BCM"]+totals["HOBCM"])/60,2),
        DUO_machine_h=round(totals["DUO"]/60,2),DGS_machine_h=round(totals["DGS"]/60,2),
        peak_coach_EA=round(max(r["coaching_EA_min"] for r in rows),3),
        total_train_minutes_EA=round(sum(r["train_minutes_lost"] for r in rows),1),
        days_failing_65_proxy=sum(not r["target_65_feasible_proxy"] for r in rows),
        rejected_BCM_starts=rejected)
    return rows,events,summary
