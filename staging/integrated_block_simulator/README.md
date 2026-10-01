# m-Work Engineering Block & Capacity Optimizer

Streamlit research simulator for multiple engineering works sharing block time, machines, punctuality/EA and train capacity.

## Main features
- m independently defined works with separate fields for work type, section, direction, from km, to km, priority, PSR, productivity and daily block need.
- Earliest start date and/or latest finish date per work.
- Central constraints for minimum passenger trains, minimum goods paths, passenger/goods speeds, network EA budget and block footprint.
- Rolling-horizon Approximate Dynamic Programming / beam-search heuristic optimizer.
- Shared machine constraints, continuous campaigns and shadow-block credit.
- Synthetic timetable and seasonal demand placeholders, with CSV upload points for real data.

## Streamlit entry point
`app/streamlit_app.py`

## Important
This is a research simulator, not an operational block-authority or certified line-capacity system.
