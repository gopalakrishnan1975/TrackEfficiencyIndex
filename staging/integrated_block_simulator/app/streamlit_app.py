import os, sys
from datetime import date
import pandas as pd
import streamlit as st
import plotly.express as px

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)

from models.domain import WorkSite, MachinePool, PlannerPolicy
from simulation.scenarios import WORK_TYPES, default_works, default_machines, default_policy
from services.demand_service import synthetic_demand, aggregate_daily
from services.timetable_service import synthetic_timetable, validate_timetable
from optimization.planner import plan

st.set_page_config(page_title="Integrated Engineering Block Simulator",layout="wide")
st.title("Integrated Engineering Block & Capacity Simulator")
st.caption("Research/staging simulator. Synthetic defaults are visibly marked and must be replaced by authorised railway data before operational use.")

with st.expander("Data provenance and placeholders",expanded=True):
    st.warning("Synthetic placeholders are used for timetable, seasonal demand, productivity, speed-restoration stages, shadow propagation and capacity screening unless you upload/enter real values. Outputs are decision-support experiments, not block authority or certified capacity.")

st.subheader("1. Work sites")
selected=st.multiselect("Add one or more macro work types",list(WORK_TYPES),default=["BCM-Plain Track","TRR"])
rows=[]
for i,wt in enumerate(selected,1):
    d=WORK_TYPES[wt]
    rows.append({"work_id":f"W{i}","work_type":wt,"section":"A-B","direction":"UP","from_km":10+(i-1)*10,"to_km":14+(i-1)*10,
                 "priority":i,"earliest_day":0,"latest_day":25+10*(i-1),"psr_kph":130,"productivity_km_per_block":d["productivity"],"block_minutes":d["block"],"continuous":True})
work_df=st.data_editor(pd.DataFrame(rows),num_rows="dynamic",use_container_width=True,key="work_editor")

st.subheader("2. Network inputs")
c1,c2,c3,c4=st.columns(4)
with c1: horizon=st.number_input("Planning horizon (days)",14,365,90)
with c2: ea_cap=st.number_input("Max weighted EA/day (min)",0.0,5000.0,250.0,10.0)
with c3: min_goods=st.number_input("Minimum goods paths/day",0,100,20)
with c4: max_block=st.number_input("Max block footprint/day (min)",60,720,360,30)
allow_shadow=st.checkbox("Allow compatible parallel/shadow blocks",value=True)

tt_file=st.file_uploader("Upload real timetable CSV (optional)",type=["csv"])
demand_file=st.file_uploader("Upload real seasonal demand CSV (optional)",type=["csv"])
if tt_file:
    timetable=validate_timetable(pd.read_csv(tt_file)); tt_source="REAL/UPLOADED"
else:
    timetable=synthetic_timetable(); tt_source="SYNTHETIC PLACEHOLDER"
if demand_file:
    demand=pd.read_csv(demand_file); demand_source="REAL/UPLOADED"
    if "coaching_demand" not in demand.columns:
        demand=aggregate_daily(demand)
else:
    demand=aggregate_daily(synthetic_demand(int(horizon))); demand_source="SYNTHETIC PLACEHOLDER"
st.info(f"Timetable: {tt_source} | Demand: {demand_source}")

with st.expander("Preview demand seasonality"):
    st.line_chart(demand.set_index("day")[["coaching_demand","goods_demand"]])

st.subheader("3. Machines/resources")
default_pool=default_machines().quantities
machine_df=pd.DataFrame([{"machine":m,"available":n,"synthetic":True} for m,n in default_pool.items()])
machine_df=st.data_editor(machine_df,use_container_width=True,key="machines")

if st.button("Run central planner",type="primary",use_container_width=True):
    works=[]
    for _,r in work_df.iterrows():
        wt=str(r.work_type); cat=WORK_TYPES.get(wt,{"machines":{}})
        works.append(WorkSite(str(r.work_id),wt,str(r.section),str(r.direction),float(r.from_km),float(r.to_km),int(r.priority),int(r.earliest_day),int(r.latest_day),float(r.psr_kph),float(r.productivity_km_per_block),int(r.block_minutes),bool(r.continuous),cat.get("machines",{}),synthetic=True))
    pool=MachinePool({str(r.machine):int(r.available) for _,r in machine_df.iterrows()})
    policy=PlannerPolicy(max_weighted_ea_min_per_day=float(ea_cap),min_goods_paths_per_day=int(min_goods),max_block_minutes_per_day=int(max_block),allow_shadow_parallelism=allow_shadow)
    sched,ea,status=plan(works,timetable,demand,pool,policy,int(horizon))
    st.session_state["result"]=(sched,ea,status)

if "result" in st.session_state:
    sched,ea,status=st.session_state["result"]
    st.subheader("4. Completion status")
    st.dataframe(status,use_container_width=True)
    if not sched.empty:
        st.subheader("5. Block / work Gantt")
        g=sched.copy(); g["Start"]=pd.to_datetime("2026-01-01")+pd.to_timedelta(g.day,unit="D"); g["Finish"]=g.Start+pd.to_timedelta(1,unit="D")
        fig=px.timeline(g,x_start="Start",x_end="Finish",y="work_id",color="work_type",hover_data=["from_km","to_km","block_minutes","network_block_footprint_min","shadow_credit_min","weighted_ea_min","goods_paths_accepted"])
        fig.update_yaxes(autorange="reversed"); st.plotly_chart(fig,use_container_width=True)

        st.subheader("6. System impacts")
        daily=sched.groupby("day",as_index=False).agg(network_block_footprint_min=("network_block_footprint_min","max"),shadow_credit_min=("shadow_credit_min","max"),weighted_ea_min=("weighted_ea_min","max"),goods_paths_accepted=("goods_paths_accepted","min"),goods_demand=("goods_demand","max"),unmet_goods=("unmet_goods","max"))
        st.dataframe(daily,use_container_width=True)
        st.line_chart(daily.set_index("day")[["weighted_ea_min","network_block_footprint_min","shadow_credit_min"]])
        st.bar_chart(daily.set_index("day")[["goods_paths_accepted","goods_demand"]])

        st.subheader("7. Train-wise network EA")
        st.dataframe(ea.sort_values(["day","train_id"]) if not ea.empty else ea,use_container_width=True,height=320)
        st.download_button("Download schedule CSV",sched.to_csv(index=False),"integrated_schedule.csv")
        st.download_button("Download train EA CSV",ea.to_csv(index=False),"train_ea.csv")
        st.download_button("Download completion status CSV",status.to_csv(index=False),"work_status.csv")

st.expander("Current model scope / next upgrades").write("""
Implemented: multiple macro work sites, shared machines, continuity, synthetic seasonal coaching/freight demand, central network-level EA constraint, train-wise EA approximation, shadow-credit approximation, residual goods-capacity screen, and completion-oriented central allocation.

Placeholders to replace with real data/models: authorised speed-restoration rules, actual timetable paths and route overlap, station dwell/headways, exact time-space staircase, block compatibility matrix, machine production distributions, seasonal commodity forecasts, passenger cancellation rules, and certified line-capacity/train-graph model. A later version can replace the greedy central planner with MILP/CP-SAT and generate a Pareto envelope over makespan, EA, cancellations and freight throughput.
""")
