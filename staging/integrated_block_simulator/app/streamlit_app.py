import os, sys
from datetime import date, timedelta
import pandas as pd
import streamlit as st

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)

from models.domain import WorkSite, MachinePool, PlannerPolicy
from simulation.scenarios import WORK_TYPES, default_machines
from services.demand_service import synthetic_demand, aggregate_daily
from services.timetable_service import synthetic_timetable, validate_timetable
from optimization.adp_planner import plan_adp, ADPConfig

st.set_page_config(page_title="m-Work Engineering Block Optimizer",layout="wide")
st.title("m-Work Engineering Block & Capacity Optimizer")
st.caption("Central ADP/heuristic planner for multiple engineering works. Synthetic values are placeholders wherever real railway data are not supplied.")

with st.expander("Model status / placeholder policy",expanded=False):
    st.warning("Research simulator only. It is not a block authority, safety authority or certified line-capacity tool.")
    st.write("Real timetable, restoration rules, productivity, machine availability, shadow geometry and demand should replace synthetic placeholders before operational use.")

st.subheader("1. Planning horizon")
p1,p2=st.columns(2)
with p1: planning_start=st.date_input("Planning start date",value=date.today())
with p2: horizon=st.number_input("Planning horizon (days)",14,365,90)

st.subheader("2. Define m engineering works")
m=st.number_input("Number of works (m)",1,20,2,1)
work_rows=[]
for i in range(1,int(m)+1):
    with st.expander(f"Work W{i}",expanded=(i<=2)):
        c1,c2,c3,c4=st.columns(4)
        with c1:
            wt=st.selectbox("Work type",list(WORK_TYPES),key=f"wt_{i}")
            wid=st.text_input("Work ID",value=f"W{i}",key=f"wid_{i}")
        with c2:
            section=st.text_input("Section",value="A-B",key=f"section_{i}")
            direction=st.selectbox("Direction",["UP","DOWN","BOTH"],key=f"dir_{i}")
        with c3:
            from_km=st.number_input("From km",0.0,5000.0,10.0+(i-1)*10,0.1,key=f"from_{i}")
            to_km=st.number_input("To km",0.0,5000.0,14.0+(i-1)*10,0.1,key=f"to_{i}")
        with c4:
            priority=st.number_input("Priority (1 highest)",1,50,i,1,key=f"pri_{i}")
            psr=st.number_input("Section PSR (km/h)",10.0,200.0,130.0,5.0,key=f"psr_{i}")

        d1,d2,d3,d4=st.columns(4)
        cat=WORK_TYPES[wt]
        with d1:
            date_mode=st.selectbox("Date constraint",["Both","Earliest start only","Latest finish only"],key=f"dmode_{i}")
        default_es=planning_start
        default_lf=planning_start+timedelta(days=25+10*(i-1))
        with d2:
            earliest=st.date_input("Earliest start date",value=default_es,key=f"es_{i}",
                                   disabled=(date_mode=="Latest finish only"))
        with d3:
            latest=st.date_input("Latest finish date",value=default_lf,key=f"lf_{i}",
                                 disabled=(date_mode=="Earliest start only"))
        with d4:
            continuous=st.checkbox("Continue campaign to end km",value=True,key=f"cont_{i}")

        e1,e2=st.columns(2)
        with e1:
            productivity=st.number_input("Progress per block (km/site-equivalent)",0.01,20.0,float(cat["productivity"]),0.05,key=f"prod_{i}")
        with e2:
            block_min=st.number_input("Block required per working day (min)",15,720,int(cat["block"]),15,key=f"blk_{i}")

        earliest_day=0 if date_mode=="Latest finish only" else max(0,(earliest-planning_start).days)
        latest_day=int(horizon)-1 if date_mode=="Earliest start only" else max(0,(latest-planning_start).days)
        work_rows.append({"work_id":wid,"work_type":wt,"section":section,"direction":direction,"from_km":from_km,"to_km":to_km,
                          "priority":priority,"earliest_day":earliest_day,"latest_day":latest_day,"psr_kph":psr,
                          "productivity":productivity,"block_minutes":block_min,"continuous":continuous})

st.subheader("3. Train-capacity, speed, EA and block constraints")
a,b,c,d=st.columns(4)
with a:
    passenger_count=st.number_input("Synthetic passenger trains/day",1,300,40)
    min_passenger=st.number_input("Minimum passenger trains to operate/day",0,300,36)
with b:
    passenger_speed=st.number_input("Passenger train speed (km/h)",20,200,110,5)
    goods_speed=st.number_input("Goods train speed (km/h)",20,120,60,5)
with c:
    goods_count=st.number_input("Synthetic freight demand trains/day",0,300,30)
    min_goods=st.number_input("Minimum goods paths/day",0,300,20)
with d:
    ea_cap=st.number_input("Network EA budget/day (weighted min)",0.0,10000.0,250.0,10.0)
    max_block=st.number_input("Maximum network block footprint/day (min)",30,1440,360,30)

x1,x2,x3,x4=st.columns(4)
with x1: max_parallel=st.number_input("Max simultaneous works",1,4,2)
with x2: lookahead=st.slider("ADP lookahead days",1,10,5)
with x3: beam_width=st.slider("ADP beam width",2,40,10)
with x4:
    objective=st.selectbox("Objective",["min_makespan","min_sum_completion"],
        format_func=lambda x:"Minimise overall completion time" if x=="min_makespan" else "Minimise sum of work completion times")
allow_shadow=st.checkbox("Allow compatible shadow/parallel blocks",value=True)

st.subheader("4. Timetable and seasonal demand")
tt_file=st.file_uploader("Upload real timetable CSV (optional)",type=["csv"])
demand_file=st.file_uploader("Upload real seasonal demand CSV (optional)",type=["csv"])
if tt_file:
    timetable=validate_timetable(pd.read_csv(tt_file)); tt_source="REAL / UPLOADED"
else:
    timetable=synthetic_timetable(passenger_count,goods_count,passenger_speed,goods_speed); tt_source="SYNTHETIC PLACEHOLDER"
if demand_file:
    demand=pd.read_csv(demand_file); demand_source="REAL / UPLOADED"
    if "coaching_demand" not in demand.columns: demand=aggregate_daily(demand)
else:
    demand=aggregate_daily(synthetic_demand(int(horizon),passenger_count,goods_count)); demand_source="SYNTHETIC PLACEHOLDER"
st.info(f"Timetable: {tt_source} | Demand: {demand_source}")
with st.expander("Demand preview"):
    st.line_chart(demand.set_index("day")[["coaching_demand","goods_demand"]])

st.subheader("5. Machine/resources")
default_pool=default_machines().quantities
machine_df=pd.DataFrame([{"machine":k,"available":v,"synthetic":True} for k,v in default_pool.items()])
machine_df=st.data_editor(machine_df,use_container_width=True,key="machine_editor")

if st.button("Optimize m-work block programme",type="primary",use_container_width=True):
    ids=[str(r["work_id"]).strip() for r in work_rows]
    if len(set(ids))!=len(ids):
        st.error("Work IDs must be unique."); st.stop()
    if min_passenger>passenger_count and not tt_file:
        st.error("Minimum passenger trains cannot exceed synthetic passenger trains/day."); st.stop()
    works=[]
    for r in work_rows:
        cat=WORK_TYPES[r["work_type"]]
        works.append(WorkSite(r["work_id"],r["work_type"],r["section"],r["direction"],float(r["from_km"]),float(r["to_km"]),
                              int(r["priority"]),int(r["earliest_day"]),int(r["latest_day"]),float(r["psr_kph"]),
                              float(r["productivity"]),int(r["block_minutes"]),bool(r["continuous"]),cat.get("machines",{}),synthetic=True))
    pool=MachinePool({str(r.machine):int(r.available) for _,r in machine_df.iterrows()})
    policy=PlannerPolicy(max_weighted_ea_min_per_day=float(ea_cap),min_passenger_trains_per_day=int(min_passenger),
                         min_goods_paths_per_day=int(min_goods),passenger_speed_kph=float(passenger_speed),
                         goods_speed_kph=float(goods_speed),max_block_minutes_per_day=int(max_block),
                         max_concurrent_works=int(max_parallel),allow_shadow_parallelism=allow_shadow,objective=objective)
    config=ADPConfig(lookahead_days=int(lookahead),beam_width=int(beam_width))
    with st.spinner("Running m-work ADP / heuristic optimization..."):
        sched,ea,status,audit=plan_adp(works,timetable,demand,pool,policy,int(horizon),config)
    st.session_state["m_result"]=(sched,ea,status,audit,planning_start)

if "m_result" in st.session_state:
    sched,ea,status,audit,planning_start=st.session_state["m_result"]
    completed=int(status.complete.sum()) if not status.empty else 0
    total=len(status)
    makespan=int(status.completion_day.dropna().max()+1) if (not status.empty and status.completion_day.notna().any()) else None
    total_block=float(sched.groupby("day").network_block_footprint_min.max().sum()) if not sched.empty else 0
    shadow=float(sched.groupby("day").shadow_credit_min.max().sum()) if not sched.empty else 0
    peak_ea=float(sched.weighted_ea_min.max()) if not sched.empty else 0
    k1,k2,k3,k4,k5=st.columns(5)
    k1.metric("Works complete",f"{completed}/{total}")
    k2.metric("Programme makespan",f"{makespan} d" if makespan else "Not complete")
    k3.metric("Network block",f"{total_block:.0f} min")
    k4.metric("Shadow credit",f"{shadow:.0f} min")
    k5.metric("Peak weighted EA",f"{peak_ea:.1f} min")

    tabs=st.tabs(["Programme","Capacity & EA","Work status","Train EA","Decision audit"])
    with tabs[0]:
        if sched.empty:
            st.warning("No feasible work allocation found under the selected hard constraints.")
        else:
            g=sched.copy()
            origin=pd.Timestamp(planning_start)
            g["Start"]=origin+pd.to_timedelta(g.day,unit="D")
            g["End"]=g["Start"]+pd.to_timedelta(1,unit="D")
            spec={"mark":{"type":"bar","cornerRadius":3},
                  "encoding":{"x":{"field":"Start","type":"temporal","title":"Date"},"x2":{"field":"End"},
                  "y":{"field":"work_id","type":"nominal","title":"Work"},
                  "color":{"field":"work_type","type":"nominal"},
                  "tooltip":[{"field":"work_id"},{"field":"work_type"},{"field":"from_km"},{"field":"to_km"},
                             {"field":"advance_km"},{"field":"weighted_ea_min"},{"field":"goods_paths_accepted"}]},
                  "height":{"step":30}}
            st.vega_lite_chart(g,spec,use_container_width=True)
            st.dataframe(g[["day","work_id","work_type","from_km","to_km","advance_km","progress_km","caution_kph","shadow_fraction"]],use_container_width=True)
    with tabs[1]:
        if not sched.empty:
            daily=sched.groupby("day",as_index=False).agg(network_block_footprint_min=("network_block_footprint_min","max"),
                shadow_credit_min=("shadow_credit_min","max"),weighted_ea_min=("weighted_ea_min","max"),
                passenger_operated=("passenger_operated","min"),goods_paths_accepted=("goods_paths_accepted","min"),
                goods_demand=("goods_demand","max"),unmet_goods=("unmet_goods","max"))
            st.line_chart(daily.set_index("day")[["weighted_ea_min","network_block_footprint_min","shadow_credit_min"]])
            st.bar_chart(daily.set_index("day")[["passenger_operated","goods_paths_accepted"]])
            st.dataframe(daily,use_container_width=True)
    with tabs[2]:
        st.dataframe(status,use_container_width=True,
            column_config={"progress_pct":st.column_config.ProgressColumn("Progress %",min_value=0,max_value=100,format="%.1f%%")})
    with tabs[3]:
        st.dataframe(ea.sort_values(["day","train_id"]) if not ea.empty else ea,use_container_width=True,height=420)
    with tabs[4]:
        st.dataframe(audit,use_container_width=True,height=460)

    if not sched.empty:
        q1,q2,q3,q4=st.columns(4)
        q1.download_button("Schedule CSV",sched.to_csv(index=False),"m_work_schedule.csv")
        q2.download_button("Train EA CSV",ea.to_csv(index=False),"m_work_train_ea.csv")
        q3.download_button("Status CSV",status.to_csv(index=False),"m_work_status.csv")
        q4.download_button("Decision audit CSV",audit.to_csv(index=False),"m_work_adp_audit.csv")

st.expander("Optimization method and current limits").write("""
This version supports an arbitrary set of m works, each with its own chainage, date window, priority, productivity, block demand, PSR and continuity rule. The central planner uses rolling-horizon ADP/beam-search heuristics to allocate blocks and machines under network-level EA, minimum passenger-service, minimum goods-path and block-footprint constraints.

For computational control, only the most urgent candidate works are expanded at each state and simultaneous actions are capped by the user-selected maximum. Shadow overlap for more than two simultaneous works is a pairwise heuristic approximation. The production version should replace it with the exact union of time-space staircases.
""")
