import io
from datetime import date
import pandas as pd
import streamlit as st
import plotly.express as px
from block_planner_v2_engine import WORK_CATALOG, schedule_works

st.set_page_config(page_title="BCM Block Planner - Staging v2", layout="wide")
st.title("BCM Block Planner - Staging v2")
st.caption("Multi-work block and caution-order planning prototype. Staging only; not an operating authority.")

st.subheader("1. Major works requiring blocks / caution orders")
seed=pd.DataFrame([
 {"work_id":"W001","work_type":"BCM-Plain Track","section":"A-B","direction":"UP","from_km":10.0,"to_km":14.0,"priority":1,"earliest_start":date.today(),"latest_finish":None,"psr_kph":110,"block_hours":3.0,"caution_kph":30,"rate_km_per_block":0.4,"continuous":True},
 {"work_id":"W002","work_type":"Through Tamping","section":"A-B","direction":"UP","from_km":14.0,"to_km":18.0,"priority":2,"earliest_start":date.today(),"latest_finish":None,"psr_kph":110,"block_hours":2.5,"caution_kph":75,"rate_km_per_block":1.5,"continuous":False},
])
works=st.data_editor(seed,num_rows="dynamic",use_container_width=True,column_config={
 "work_type":st.column_config.SelectboxColumn("Work type",options=list(WORK_CATALOG)),
 "priority":st.column_config.NumberColumn("Priority (1 highest)",min_value=1,max_value=5,step=1),
 "continuous":st.column_config.CheckboxColumn("Continue until end km"),
})

st.subheader("2. Timetable")
st.write("Upload CSV with: train_id, train_class, section, direction, enter_min, exit_min, max_speed_kph; optional service_date.")
upload=st.file_uploader("Timetable CSV",type=["csv"])
if upload:
    timetable=pd.read_csv(upload)
else:
    timetable=pd.DataFrame([
      {"train_id":"P001","train_class":"Coaching","section":"A-B","direction":"UP","enter_min":360,"exit_min":390,"max_speed_kph":110},
      {"train_id":"P002","train_class":"Coaching","section":"A-B","direction":"UP","enter_min":420,"exit_min":450,"max_speed_kph":110},
      {"train_id":"G001","train_class":"Goods","section":"A-B","direction":"UP","enter_min":480,"exit_min":540,"max_speed_kph":60},
      {"train_id":"G002","train_class":"Goods","section":"A-B","direction":"UP","enter_min":600,"exit_min":660,"max_speed_kph":60},
    ])
st.dataframe(timetable,use_container_width=True)

c1,c2,c3=st.columns(3)
with c1: start=st.date_input("Planning start date",value=date.today())
with c2: horizon=st.number_input("Planning horizon (days)",30,730,120,10)
with c3: max_blocks=st.number_input("Maximum major blocks/day",1,4,1)

if st.button("Generate integrated block plan",type="primary",use_container_width=True):
    try:
        sched, impacts, status=schedule_works(works,timetable,start,int(horizon),int(max_blocks))
    except Exception as e:
        st.error(str(e)); st.stop()
    st.session_state["v2_results"]=(sched,impacts,status)

if "v2_results" in st.session_state:
    sched,impacts,status=st.session_state["v2_results"]
    st.subheader("3. Work programme")
    st.dataframe(status,use_container_width=True)
    if not sched.empty:
        st.subheader("4. Gantt / block calendar")
        gantt=sched.copy(); gantt["Start"]=pd.to_datetime(gantt["date"]); gantt["Finish"]=gantt["Start"]+pd.to_timedelta(gantt["block_hours"],unit="h")
        gantt["Task"]=gantt["work_id"]+" | "+gantt["work_type"]+" | "+gantt["section"]+" | "+gantt["from_km"].astype(str)+"-"+gantt["to_km"].astype(str)
        fig=px.timeline(gantt,x_start="Start",x_end="Finish",y="Task",color="work_type",hover_data=["priority","total_EA_min","goods_paths_lost"])
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig,use_container_width=True)

        st.subheader("5. Daily operating impact")
        daily=sched.groupby("date",as_index=False).agg(block_hours=("block_hours","sum"),total_EA_min=("total_EA_min","sum"),goods_paths_lost=("goods_paths_lost","sum"),estimated_goods_paths=("estimated_goods_paths","min"))
        st.dataframe(daily,use_container_width=True)
        st.bar_chart(daily.set_index("date")[["goods_paths_lost"]])

        st.subheader("6. Train-wise Engineering Allowance")
        st.dataframe(impacts.sort_values(["date","train_id"]),use_container_width=True)
        st.download_button("Download block schedule CSV",sched.to_csv(index=False),"block_schedule.csv")
        st.download_button("Download train-wise EA CSV",impacts.to_csv(index=False),"train_ea.csv")
        st.download_button("Download work status CSV",status.to_csv(index=False),"work_status.csv")

st.expander("Planning-policy rules implemented").write("""
- Supported major-work types: BCM plain track, BCM point-machine locations, CTR/Primary via PQRS, CTR/Primary via TRT, TRR, through tamping and crossovers.
- Each work has section, km limits, priority, earliest start, latest finish, PSR, block spell, caution speed and productivity.
- A work marked continuous becomes the active work front and is scheduled on every eligible planning day until its end km is reached; the planner will not voluntarily switch to another major work during that run.
- EA is computed train-by-train from the uploaded timetable and the active caution-order length using each train's speed ceiling and section PSR.
- Goods-path impact is a screening proxy based on block minutes + goods EA divided by assumed headway. It is not a certified line-capacity calculation.
- Production values, caution speeds and block durations are editable placeholders and must be validated against current manuals, field output and authorised instructions.
""")