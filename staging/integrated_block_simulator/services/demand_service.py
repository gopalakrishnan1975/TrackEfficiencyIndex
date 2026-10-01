import math
import pandas as pd

def synthetic_demand(horizon_days: int = 90, base_passenger:int=40, base_goods:int=30) -> pd.DataFrame:
    rows=[]
    commodities=["coal","cement","foodgrain"]
    for d in range(horizon_days):
        weekly = 1.0 + 0.08*math.sin(2*math.pi*d/7)
        seasonal = 1.0 + 0.18*math.sin(2*math.pi*d/60)
        regular = int(base_passenger)
        tod = max(0, round(0.08*base_passenger + 0.08*base_passenger*max(0, math.sin(2*math.pi*(d-10)/30))))
        diverted = max(0,round(0.05*base_passenger)) if 28 <= d % 60 <= 38 else 0
        goods_total = max(0, round(base_goods*weekly*seasonal))
        shares={"coal":0.52,"cement":0.28,"foodgrain":0.20}
        for c in commodities:
            rows.append({"day":d,"commodity":c,"goods_demand":round(goods_total*shares[c]),
                         "regular_coaching":regular,"tod_trains":tod,"diverted_trains":diverted,
                         "synthetic":True})
    return pd.DataFrame(rows)

def aggregate_daily(demand: pd.DataFrame) -> pd.DataFrame:
    g=(demand.groupby("day",as_index=False)
       .agg(goods_demand=("goods_demand","sum"),
            regular_coaching=("regular_coaching","max"),
            tod_trains=("tod_trains","max"),
            diverted_trains=("diverted_trains","max"),
            synthetic=("synthetic","max")))
    g["coaching_demand"]=g.regular_coaching+g.tod_trains+g.diverted_trains
    return g
