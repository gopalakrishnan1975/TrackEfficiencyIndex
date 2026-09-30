# BCM–Duomatic Block Policy Lab

A shareable **Streamlit research simulator** for ballast-cleaning and staged speed-restoration planning on a railway block section.

## Deploy on Streamlit Community Cloud

1. Sign in to https://share.streamlit.io with your GitHub account.
2. Select **Create app** and choose the repository **gopalakrishnan1975/TrackEfficiencyIndex**.
3. Choose branch **main** and the entry-point file **streamlit_app.py**.
4. Deploy. Streamlit will install dependencies from **requirements.txt**.
5. Open the generated URL to share it. Configure access controls according to your hosting arrangement.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## What can users change?

- Two conventional BCMs or one synthetic high-output BCM.
- One or two Duomatic tampers, and one or two DGS stabilisers.
- Section length in 400 m increments; default 12 km.
- Maximum 2.5, 3 or 4 hour traffic possession; 1–6 BCM days per week.
- Clearance toward the rear station, ahead station, or nearest feasible endpoint.
- Separately authorised 30/40 km/h post-block workspot restrictions.
- Coaching and goods train counts and speeds; optional coaching EA ceiling.
- Search objective: fewest block-hours, earliest complete restoration or lowest total train-minutes lost.

The interface displays estimated completion date, total booked traffic block-hours, combined machine-hours, patch-by-patch speed milestones and a **simplified fluid capacity proxy**, plus downloadable CSV and JSON results.

## Important limitations

**Demonstration only:** all machine productivities, restoration-stage eligibility, movement constraints and capacity estimates are synthetic. The algorithm searches a finite family of weekly block-day policies, with a greedy local dispatcher; it is **not** globally optimal dynamic programming. BCM work packets of 400 m cannot be partially completed across days in this version. It does not construct a working train graph or verify signalling headways, and its capacity estimates are not certified train-path counts.

The cutter bar is assumed removed from beneath the running track at the end of each possession. Retention outside the track and the worksite's temporary speed restriction are separate conditions. Prescribed IRPWM Engineering inspections, consolidation, work completion and independent approvals determine actual permissible speeds. Do not treat modelled stages as automatic speed-relaxation permission.

Do not upload non-public railway operational records, safety-sensitive infrastructure details, or personal information to a publicly shared app.

## Source files

- `streamlit_app.py`: interactive interface
- `web_optimizer.py`: finite schedule-template search and objective ordering
- `policy_simulator_two_ends.py`: endpoint-aware daily simulator
- `requirements.txt`: pinned dependency ranges

For production use: calibrate machine rates with actual block logs, model partial work carry-over, add real timetable/signal-route constraints, and validate the permissible speed stages with Engineering.
