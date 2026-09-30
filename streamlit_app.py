"""BCM Block Planner — interactive synthetic maintenance policy simulator."""
import json
import pandas as pd
import streamlit as st
from web_optimizer import optimize

st.set_page_config(page_title="BCM Block Planner", page_icon="🚆", layout="wide", initial_sidebar_state="collapsed")
st.title("BCM Block Planner")
st.markdown("### Enter your operating inputs")
st.write("Set the available machines, traffic demand, block policy, and Engineering Allowance below. On phones, all controls appear on this page; the sidebar is not required.")
st.warning("Research demonstration only. Synthetic speeds, workloads, stage dates and line capacity are not operational authority.")
st.caption("Cutter bar is removed from the running track. The 30/40 km/h workspot restriction is separately authorised.")

with st.form("planner_inputs", clear_on_submit=False):
    st.header("Fleet")
    fleet = st.selectbox("Ballast cleaning", ["2BCM", "HOBCM"], format_func=lambda x: "Two conventional BCMs" if x == "2BCM" else "One high-output BCM")
    duomatics = st.radio("Duomatics", [1, 2], horizontal=True)
    dgs = st.radio("DGS / DTS machines", [1, 2], horizontal=True)
    st.header("Possessions and route")
    section = st.number_input("Section length (km)", 0.4, 40.0, 12.0, 0.4)
    block = st.selectbox("Maximum block spell (hours)", [2.5, 3.0, 4.0], index=1)
    days = st.slider("Maximum BCM days/week", 1, 6, 4)
    station_exit = st.selectbox("Clear machine to station", ["nearest", "rear", "ahead"])
    spots = st.multiselect("Authorised workspot speed options (km/h)", [30, 40], default=[30, 40])
    st.header("Demand and Engineering Allowance")
    ncoach = st.number_input("Coaching trains/day", min_value=1, max_value=250, value=40)
    ngoods = st.number_input("Goods trains/day", min_value=1, max_value=250, value=25)
    vc = st.number_input("Coaching speed ceiling (km/h)", min_value=30, max_value=160, value=130)
    vg = st.number_input("Goods speed ceiling (km/h)", min_value=20, max_value=120, value=60)
    limit = st.checkbox("Apply coaching EA ceiling", value=True)
    ea = st.number_input("EA ceiling (minutes/train)", min_value=0.1, max_value=30.0, value=5.0, step=0.5, disabled=not limit)
    objective = st.selectbox("Optimisation objective", ["min_block_hours", "finish_then_block_then_delay", "min_total_train_minutes"],
        format_func=lambda v: {"min_block_hours": "Minimum booked block-hours", "finish_then_block_then_delay": "Earliest full restoration", "min_total_train_minutes": "Minimum train-minutes lost"}[v])
    submitted = st.form_submit_button("Optimise block policy", type="primary", use_container_width=True)

@st.cache_data(show_spinner=False)
def solve(parameters):
    return optimize(json.loads(parameters))

if submitted:
    if not spots:
        st.error("Choose an authorised workspot speed.")
        st.stop()
    if abs(round(section/0.4)*0.4 - section) > 1e-6:
        st.error("Section length must be divisible into 400 m patches.")
        st.stop()
    parameters = dict(fleet_type=fleet, duomatics=duomatics, dgs_machines=dgs,
       section_km=section, coaching_trains=ncoach, goods_trains=ngoods,
       coach_speed_kph=vc, goods_speed_kph=vg, station_exit=station_exit,
       max_block_hours=block, max_workdays_per_week=days,
       coach_EA_cap_min=ea if limit else None, horizon_days=120,
       allowed_spot_speeds=spots, objective=objective)
    with st.spinner("Evaluating weekly maintenance and restoration templates..."):
        results = solve(json.dumps(parameters, sort_keys=True))
    st.session_state["run"] = (parameters, *results)

if "run" in st.session_state:
    parameters, best, comparisons, feasible = st.session_state["run"]
    st.write(f"**Policies evaluated:** {len(comparisons)} | **Passing synthetic feasibility screens:** {feasible}")
    if best is None:
        st.error("No tested policy fully restored the section within the horizon while satisfying all proxy constraints. This does not prove operational infeasibility.")
    else:
        _, _, comparison, cfg, rows, events, summary = best
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Full MPS restoration", f"Day {summary['finish_day']}")
        c2.metric("Traffic block-hours", f"{summary['total_block_h']:.1f}")
        c3.metric("Peak coaching EA", f"{summary['peak_coach_EA']:.2f} min")
        c4.metric("Minimum paths/day proxy", f"{comparison['min_proxy_paths_day']:.2f}")
        st.write(f"**BCM working weekdays (Mon=1):** {comparison['bcm_days']}; **workspot speed:** {comparison['workspot_speed_kph']} km/h.")
        st.write(f"**Machine-hours, all machines of each type combined:** cleaning {summary['BCM_or_HOBCM_machine_h']:.2f}; Duomatic {summary['DUO_machine_h']:.2f}; DGS {summary['DGS_machine_h']:.2f}.")
        daily = pd.DataFrame(rows)
        milestones = pd.DataFrame(events)
        st.subheader("Restoration progress")
        st.line_chart(daily.set_index("day")[["cleaned_km", "restored_130_km"]])
        st.subheader("Engineering Allowance (minutes per train)")
        st.line_chart(daily.set_index("day")[["coaching_EA_min", "goods_EA_min"]])
        st.subheader("Estimated fluid capacity (not certified paths)")
        st.line_chart(daily.set_index("day")[["fluid_paths_proxy"]])
        st.subheader("Daily actions")
        st.dataframe(daily, use_container_width=True)
        st.subheader("Individual 400-m patch milestones")
        st.dataframe(milestones, use_container_width=True)
        st.download_button("Daily plan CSV", daily.to_csv(index=False), file_name="selected_daily.csv")
        st.download_button("Patch milestones CSV", milestones.to_csv(index=False), file_name="patch_milestones.csv")
        st.download_button("Selected plan JSON", json.dumps(cfg, indent=2), file_name="selected_plan.json")
    st.subheader("All tested policies")
    comparison_df = pd.DataFrame(comparisons)
    st.dataframe(comparison_df, use_container_width=True)
    st.download_button("Policy search CSV", comparison_df.to_csv(index=False), file_name="policy_search.csv")
else:
    st.info("Enter your inputs in the form above, then select Optimise block policy.")

with st.expander("Model limitations"):
    st.write("Finite weekly-template search, not exact DP. A 400 m BCM patch must fit into a single possession; work carry-over is not implemented. Speed stages are synthetic, not automatic IRPWM authorisation. Machine movements use a simplified station-endpoint rule, and the capacity proxy excludes train-graph and signalling interactions.")
