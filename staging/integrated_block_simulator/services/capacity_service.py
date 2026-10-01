import pandas as pd

def capacity_screen(daily_demand: pd.Series, timetable: pd.DataFrame, block_capacity_minutes: float,
                    ea: pd.DataFrame, headway_min: float=7.0, passenger_cancellations: int=0,
                    min_passenger_trains: int=0) -> dict:
    """Synthetic capacity screen, not a certified line-capacity calculation."""
    coaching=int(daily_demand.coaching_demand)
    goods_dem=int(daily_demand.goods_demand)
    passenger_ea=float(ea.loc[ea.train_class.str.lower().eq("coaching"),"ea_min"].sum()) if len(ea) else 0.0
    goods_ea=float(ea.loc[ea.train_class.str.lower().eq("goods"),"ea_min"].sum()) if len(ea) else 0.0
    passenger_operated=max(0,coaching-int(passenger_cancellations))
    if passenger_operated < int(min_passenger_trains):
        return {
            "coaching_demand":coaching,"passenger_operated":passenger_operated,
            "passenger_cancellations":passenger_cancellations,"passenger_feasible":False,
            "goods_demand":goods_dem,"goods_paths_available":0,"goods_paths_accepted":0,
            "unmet_goods":goods_dem,"capacity_minutes_consumed":1440.0,
        }
    effective_lost=max(0.0,block_capacity_minutes)+0.35*passenger_ea+0.5*goods_ea
    # SYNTHETIC PLACEHOLDER: 5 minutes per coaching train and a fixed headway proxy.
    nominal_goods_slots=max(0, round((1440 - passenger_operated*5.0 - effective_lost)/max(headway_min,1)))
    accepted=min(goods_dem,nominal_goods_slots)
    return {
        "coaching_demand":coaching,"passenger_operated":passenger_operated,
        "passenger_cancellations":passenger_cancellations,"passenger_feasible":True,
        "goods_demand":goods_dem,"goods_paths_available":nominal_goods_slots,
        "goods_paths_accepted":accepted,"unmet_goods":max(0,goods_dem-accepted),
        "capacity_minutes_consumed":effective_lost,
    }
