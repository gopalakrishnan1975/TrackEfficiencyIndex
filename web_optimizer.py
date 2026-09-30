"""Finite weekly policy-template optimiser for the BCM–Duomatic Streamlit app."""
from itertools import combinations
from policy_simulator_two_ends import run

def optimize(settings):
    """Return (selected_policy_record, comparison_rows, feasible_count).

    Each selected record is (feasible, objective_key, comparison, config,
    daily_rows, patch_events, summary). This is NOT global DP optimisation.
    """
    max_days=int(settings["max_workdays_per_week"])
    templates=[days for k in range(1,max_days+1) for days in combinations(range(6),k)]
    ranked=[]
    for days in templates:
        for spot in settings["allowed_spot_speeds"]:
            for restore_hours in sorted({2.5,float(settings["max_block_hours"])}):
                cfg=dict(section_km=settings["section_km"],
                    coaching_trains=settings["coaching_trains"],goods_trains=settings["goods_trains"],
                    coach_speed_kph=settings["coach_speed_kph"],goods_speed_kph=settings["goods_speed_kph"],
                    bcm_machines=2 if settings["fleet_type"]=="2BCM" else 0,
                    duomatics=int(settings["duomatics"]),dgs_machines=int(settings["dgs_machines"]),
                    station_exit=settings["station_exit"],block_hours=settings["max_block_hours"],
                    horizon_days=settings["horizon_days"],coach_EA_cap_min=settings["coach_EA_cap_min"],
                    retain_cutter_outside=spot==30,bcm_days_of_week=list(days),
                    restoration_days_of_week=list(range(6)))
                for _ in range(4):
                    rows,events,summary=run(cfg,"browser")
                    shorter={str(row["day"]):dict(block_hours=restore_hours,allow_bcm=False,allow_restoration=True)
                             for row in rows if row["block_hours"]>0
                             and row["BCM_packets_today"]==0
                             and row["DUO_packing_jobs"]+row["DGS_stabilisation_jobs"]>0}
                    if shorter==cfg.get("daily_actions",{}): break
                    cfg["daily_actions"]=shorter
                rows,events,summary=run(cfg,"browser")
                minimum_paths=min(row["fluid_paths_proxy"] for row in rows)
                valid=(summary["completed"] and summary["days_failing_65_proxy"]==0
                    and (settings["coach_EA_cap_min"] is None
                         or summary["peak_coach_EA"]<=settings["coach_EA_cap_min"]+1e-7))
                comparison=dict(bcm_days=",".join(str(d+1) for d in days),
                   workspot_speed_kph=spot,restoration_block_h=restore_hours,
                   complete=summary["completed"],feasible_proxy=valid,finish_day=summary["finish_day"],
                   block_h=summary["total_block_h"],
                   machine_h_bcm=summary["BCM_or_HOBCM_machine_h"],
                   machine_h_duomatic=summary["DUO_machine_h"],
                   machine_h_dgs=summary["DGS_machine_h"],
                   peak_coach_EA=summary["peak_coach_EA"],
                   min_proxy_paths_day=round(minimum_paths,2),
                   cumulative_train_min_lost=summary["total_train_minutes_EA"])
                objective=settings["objective"]
                if objective=="min_block_hours":
                    key=(summary["total_block_h"],summary["finish_day"],summary["total_train_minutes_EA"])
                elif objective=="min_total_train_minutes":
                    key=(summary["total_train_minutes_EA"],summary["finish_day"],summary["total_block_h"])
                else:
                    key=(summary["finish_day"],summary["total_block_h"],summary["total_train_minutes_EA"])
                ranked.append((valid,key,comparison,cfg,rows,events,summary))
    feasible=[record for record in ranked if record[0]]
    return (min(feasible,key=lambda x:x[1]) if feasible else None,
            [record[2] for record in ranked],len(feasible))
