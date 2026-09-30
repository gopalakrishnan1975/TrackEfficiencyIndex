# Integrated Engineering Block & Capacity Simulator

Research/staging Streamlit simulator implementing the centralised architecture from the two-work technical manuscript.

## What is implemented
- Multiple macro work sites, each with its own production rate, block requirement, continuity and machine needs.
- Central planner controls blocks and machines; EA is **not allocated by work**. It is calculated at network/train level from the combined active restriction profile.
- Synthetic passenger seasonality: regular + TOD/special + diverted traffic.
- Synthetic commodity-based freight demand.
- Shadow-block capacity credit based on a simplified time-space projection.
- Train-wise EA approximation and a residual goods-path capacity screen.
- Completion-oriented central allocation subject to EA, machine and goods-path constraints.
- Streamlit UI, Gantt chart and CSV exports.

## Synthetic-data policy
Every synthetic/default dataset is explicitly marked. Replace these with authorised real data before any operational use:
- timetable and path data;
- work productivity;
- speed-restoration stages;
- seasonal demand;
- machine availability;
- block compatibility;
- time-space shadow propagation;
- capacity/headway model.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

## Streamlit Cloud
Set the app entry point to `app/streamlit_app.py` and install from `requirements.txt`.

## Real timetable CSV
Required columns:
`train_id, train_class, section, direction, enter_min, exit_min, max_speed_kph`
Optional: `weight, synthetic`.

## Real demand CSV
Either provide daily aggregate columns:
`day, coaching_demand, goods_demand`

or commodity rows:
`day, commodity, goods_demand, regular_coaching, tod_trains, diverted_trains`.

## Important limitation
This is a research simulator, not a block-authority, safety, timetable-certification or line-capacity system.
