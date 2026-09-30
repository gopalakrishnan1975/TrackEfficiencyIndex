import os, sys
import pandas as pd
import streamlit as st

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)

from models.domain import WorkSite, MachinePool, PlannerPolicy
from simulation.scenarios import WORK_TYPES, default_machines
from services.demand_service import synthetic_demand, aggregate_daily
from services.timetable_service import synthetic_timetable, validate_timetable
from optimization.adp_planner import plan_adp, ADPConfig

st.set_page_config(page_title="Integrated Engineering Block Optimizer",layout="wide")
st.title("Integrated Engineering Block & Capacity Optimizer")
st.caption("ADP rollout + heuristic central planner. Research/staging simulator; synthetic placeholders are explicitly labelled.")

with st.expander("Model status and data provenance",expanded=False):
    st.warning("Decision-support simulator only. Synthetic placeholders remain for timetable, demand, production, restoration rules, shadow geometry and capacity where real data are not supplied.")
    st.write("Optimizer: limited-horizon Approximate Dynamic Programming (beam-search rollout) with an approximate terminal value function, hard EA/capacity constraints, continuity, shared machines and shadow-credit heuristics.")

st.subheader("1. Macro engineering works")
selected=st.multiselect("Select one or more work types",list(WORK_TYPES),default=["BCM-Plain Track","TRR"])
rows=[]
for i,wt in enumerate(selected,1):
    d=WORK_TYPES[wt]
    rows.append({"work_id":f"W{i}","work_type":wt,"section":"A-B","direction":"UP","from_km":10+(i-1)*10,"to_km":14+(i-1)*10,
                 "priority":i,"earliest_day":0,"latest_day":25+10*(i-1),"psr_kph":130,
                 "productivity_km_per_block":d["productivity"],"block_minutes":d["block"],"continuous":True})
work_df=st.data_editor(pd.DataFrame(rows),num_rows="dynamic",use_container_width=True,key="work_editor",
    column_config={"priority":st.column_config.NumberColumn("Priority",min_value=1,max_value=20,step=1),
                   "continuous":st.column_config.CheckboxColumn("Continuous campaign")})

st.subheader("2. Central constraints and ADP controls")
a,b,c,d=st.columns(4)
with a: horizon=st.number_input("Planning horizon (days)",14,365,90)
with b: ea_cap=st.number_input("Max weighted EA/day",0.0,5000.0,250.0,10.0)
with c: min_goods=st.number_input("Minimum goods paths/day",0,100,20)
with d: max_block=st.number_input("Max block footprint/day (min)",60,720,360,30)

e,f,g=st.columns(3)
with e: lookahead=st.slider("ADP lookahead (days)",1,10,5)
with f: beam_width=st.slider("Beam width",2,30,8)
with g: objective=st.selectbox("Completion objective",["min_makespan","min_sum_completion"],
    format_func=lambda x:"Minimise programme makespan" if x=="min_makespan" else "Minimise sum of work completion times")
allow_shadow=st.checkbox("Allow compatible parallel / shadow blocks",value=True)

st.subheader("3. Timetable and seasonal demand")
tt_file=st.file_uploader("Upload real timetable CSV (optional)",type=["csv"])
demand_file=st.file_uploader("Upload real seasonal demand CSV (optional)",type=["csv"])
if tt_file:
    timetable=validate_timetable(pd.read_csv(tt_file)); tt_source="REAL / UPLOADED"
else:
    timetable=synthetic_timetable(); tt_source="SYNTHETIC PLACEHOLDER"
if demand_file:
    demand=pd.read_csv(demand_file); demand_source="REAL / UPLOADED"
    if "coaching_demand" not in demand.columns: demand=aggregate_daily(demand)
else:
    demand=aggregate_daily(synthetic_demand(int(horizon))); demand_source="SYNTHETIC PLACEHOLDER"
st.info(f"Timetable: {tt_source}  |  Demand: {demand_source}")
with st.expander("Demand seasonality preview",expanded=False):
    st.line_chart(demand.set_index("day")[["coaching_demand","goods_demand"]])

st.subheader("4. Machines / resources")
default_pool=default_machines().quantities
machine_df=pd.DataFrame([{"machine":m,"available":n,"synthetic":True} for m,n in default_pool.items()])
machine_df=st.data_editor(machine_df,use_container_width=True,key="machines")

if st.button("Optimize integrated block programme",type="primary",use_container_width=True):
    if work_df.empty:
        st.error("Add at least one work site."); st.stop()
    works=[]
    for _,r in work_df.iterrows():
        wt=str(r.work_type); cat=WORK_TYPES.get(wt,{"machines":{}})
        works.append(WorkSite(str(r.work_id),wt,str(r.section),str(r.direction),float(r.from_km),float(r.to_km),int(r.priority),
                              int(r.earliest_day),int(r.latest_day),float(r.psr_kph),float(r.productivity_km_per_block),
                              int(r.block_minutes),bool(r.continuous),cat.get("machines",{}),synthetic=True))
    pool=MachinePool({str(r.machine):int(r.available) for _,r in machine_df.iterrows()})
    policy=PlannerPolicy(max_weighted_ea_min_per_day=float(ea_cap),min_goods_paths_per_day=int(min_goods),
                         max_block_minutes_per_day=int(max_block),allow_shadow_parallelism=allow_shadow,objective=objective)
    config=ADPConfig(lookahead_days=int(lookahead),beam_width=int(beam_width))
    with st.spinner("Running ADP rollout / heuristic optimization..."):
        sched,ea,status,audit=plan_adp(works,timetable,demand,pool,policy,int(horizon),config)
    st.session_state["result"]=(sched,ea,status,audit)

if "result" in st.session_state:
    sched,ea,status,audit=st.session_state["result"]
    completed=int(status.complete.sum()) if not status.empty else 0
    total=len(status)
    makespan=int(status.completion_day.dropna().max()+1) if (not status.empty and status.completion_day.notna().any()) else None
    total_block=float(sched.groupby("day").network_block_footprint_min.max().sum()) if not sched.empty else 0
    shadow=float(sched.groupby("day").shadow_credit_min.max().sum()) if not sched.empty else 0
    max_ea=float(sched.weighted_ea_min.max()) if not sched.empty else 0
    unmet=int(sched.groupby("day").unmet_goods.max().sum()) if not sched.empty else 0

    k1,k2,k3,k4,k5,k6=st.columns(6)
    k1.metric("Works complete",f"{completed}/{total}")
    k2.metric("Makespan",f"{makespan} d" if makespan else "Not complete")
    k3.metric("Network block",f"{total_block:.0f} min")
    k4.metric("Shadow credit",f"{shadow:.0f} min")
    k5.metric("Peak weighted EA",f"{max_ea:.1f} min")
    k6.metric("Unmet goods",str(unmet))

    tabs=st.tabs(["Programme","Capacity & EA","Work status","Train EA","Decision audit"])
    with tabs[0]:
        if sched.empty:
            st.warning("No engineering action was feasible under the selected hard constraints.")
        else:
            g=sched.copy()
            origin=pd.Timestamp("2026-01-01")
            g["Start"]=origin+pd.to_timedelta(g.day,unit="D")
            g["End"]=g["Start"]+pd.to_timedelta(1,unit="D")
            gantt={"mark":{"type":"bar","cornerRadius":3},
              "encoding":{"x":{"field":"Start","type":"temporal","title":"Planning date"},"x2":{"field":"End"},
                "y":{"field":"work_id","type":"nominal","title":"Work","sort":None},
                "color":{"field":"work_type","type":"nominal","legend":{"title":"Work type"}},
                "tooltip":[{"field":"work_id"},{"field":"work_type"},{"field":"from_km"},{"field":"to_km"},
                           {"field":"advance_km"},{"field":"caution_kph"},{"field":"weighted_ea_min"},
                           {"field":"goods_paths_accepted"},{"field":"shadow_credit_min"}]},
              "height":{"step":34}}
            st.vega_lite_chart(g,gantt,use_container_width=True)
            st.dataframe(g[["day","work_id","work_type","from_km","to_km","advance_km","progress_km","caution_kph","shadow_fraction"]],use_container_width=True)

    with tabs[1]:
        if not sched.empty:
            daily=sched.groupby("day",as_index=False).agg(network_block_footprint_min=("network_block_footprint_min","max"),
                shadow_credit_min=("shadow_credit_min","max"),weighted_ea_min=("weighted_ea_min","max"),
                goods_paths_accepted=("goods_paths_accepted","min"),goods_demand=("goods_demand","max"),
                unmet_goods=("unmet_goods","max"))
            st.line_chart(daily.set_index("day")[["weighted_ea_min","network_block_footprint_min","shadow_credit_min"]])
            st.bar_chart(daily.set_index("day")[["goods_paths_accepted","goods_demand"]])
            st.dataframe(daily,use_container_width=True)

    with tabs[2]:
        if not status.empty:
            st.dataframe(status,use_container_width=True,
                column_config={"progress_pct":st.column_config.ProgressColumn("Progress %",min_value=0,max_value=100,format="%.1f%%")})

    with tabs[3]:
        st.dataframe(ea.sort_values(["day","train_id"]) if not ea.empty else ea,use_container_width=True,height=420)

    with tabs[4]:
        st.caption("Decision audit: ADP look-ahead path, candidate actions and expanded nodes for each implemented decision.")
        st.dataframe(audit,use_container_width=True,height=460)

    if not sched.empty:
        c1,c2,c3,c4=st.columns(4)
        c1.download_button("Schedule CSV",sched.to_csv(index=False),"integrated_schedule.csv")
        c2.download_button("Train EA CSV",ea.to_csv(index=False),"train_ea.csv")
        c3.download_button("Work status CSV",status.to_csv(index=False),"work_status.csv")
        c4.download_button("Decision audit CSV",audit.to_csv(index=False),"adp_decision_audit.csv")

st.expander("Optimization method and limitations").write("""
The optimizer is a practical Approximate Dynamic Programming heuristic. Each planning day it enumerates feasible block actions, including compatible pairs, simulates their impact on progress, speed stage, network EA, shadow credit and residual goods capacity, and performs a limited-horizon beam-search rollout. A terminal value function estimates remaining completion time, deadline pressure and shared-machine bottlenecks. The first action on the best rollout path is implemented and the process repeats the next day.

This is rolling-horizon ADP/heuristic optimization, not a proof of global optimality. Synthetic production, speed-restoration, shadow and capacity models must be replaced by authorised data/models for operational use.
""")
